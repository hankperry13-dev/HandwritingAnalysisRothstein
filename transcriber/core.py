"""Core transcription logic: build vision requests and interpret responses."""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_MAX_TOKENS = 32000

# Claude rejects images larger than 5 MB; Opus 4.8 reads detail up to 2576 px
# on the long edge, so anything bigger only costs tokens without adding fidelity.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_LONG_EDGE_PX = 2576

IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

SUPPORTED_SUFFIXES = set(IMAGE_MEDIA_TYPES) | {".pdf"}

SYSTEM_PROMPT = """\
You are an expert paleographer and archivist who specializes in transcribing \
handwritten cursive documents from archival collections: letters, diaries, \
ledgers, deeds, meeting minutes, and similar materials. You are experienced \
with faded ink, bleed-through, damaged or stained paper, cross-writing, and \
historical letterforms (e.g. the long s, superscript abbreviations, older \
spelling conventions).

Transcribe the document following these conventions:

1. Transcribe exactly what is written. Preserve original spelling, \
capitalization, punctuation, and abbreviations — do not modernize or correct.
2. Preserve the document's line breaks and paragraph structure.
3. Mark uncertain readings as [word?]. If two readings are plausible, use \
[word1?/word2?].
4. Mark unreadable text as [illegible] (or [3 words illegible] when you can \
count the words).
5. Represent the author's own edits: [crossed out: text], [inserted: text], \
[in margin: text].
6. Note structural features in square brackets where they occur: [page 2], \
[written vertically in left margin], [seal], [letterhead: ...].
7. If parts of the page are printed rather than handwritten (forms, \
letterhead), transcribe them too and note that they are printed.

After the transcription, add a "Notes" section covering: the overall \
legibility and condition of the document; any dates, names, and places you \
identified; your most significant uncertain readings and why; and anything \
that would help an archivist catalog the item. If the user supplied context \
about the collection, use it to inform ambiguous readings, but never invent \
text that is not supported by the image.

Format your answer as Markdown with a "## Transcription" section followed by \
a "## Notes" section.\
"""

JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "transcription": {
            "type": "string",
            "description": (
                "Full transcription preserving line breaks, using [word?] for "
                "uncertain readings and [illegible] for unreadable text."
            ),
        },
        "uncertain_readings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "reading": {"type": "string"},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["reading", "alternatives", "reason"],
                "additionalProperties": False,
            },
        },
        "dates_mentioned": {"type": "array", "items": {"type": "string"}},
        "people_mentioned": {"type": "array", "items": {"type": "string"}},
        "places_mentioned": {"type": "array", "items": {"type": "string"}},
        "legibility": {
            "type": "string",
            "enum": ["excellent", "good", "fair", "poor", "very poor"],
        },
        "notes": {"type": "string"},
    },
    "required": [
        "transcription",
        "uncertain_readings",
        "dates_mentioned",
        "people_mentioned",
        "places_mentioned",
        "legibility",
        "notes",
    ],
    "additionalProperties": False,
}


@dataclass
class TranscriptionResult:
    source: Path
    text: str
    model: str
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"


def _downscale_image(data: bytes, suffix: str) -> bytes | None:
    """Downscale an oversized image with Pillow, if it is installed."""
    try:
        from PIL import Image
    except ImportError:
        return None

    with Image.open(io.BytesIO(data)) as img:
        long_edge = max(img.size)
        if long_edge > MAX_LONG_EDGE_PX:
            scale = MAX_LONG_EDGE_PX / long_edge
            img = img.resize(
                (round(img.width * scale), round(img.height * scale)),
                Image.LANCZOS,
            )
        buf = io.BytesIO()
        if suffix in (".jpg", ".jpeg"):
            img = img.convert("RGB")
            img.save(buf, format="JPEG", quality=90)
        else:
            img.save(buf, format="PNG")
    return buf.getvalue()


def _build_source_block(path: Path) -> tuple[dict, list[str]]:
    """Return the image/document content block for a file, plus any warnings."""
    suffix = path.suffix.lower()
    data = path.read_bytes()
    warnings: list[str] = []

    if suffix == ".pdf":
        return (
            {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(data).decode("ascii"),
                },
            },
            warnings,
        )

    media_type = IMAGE_MEDIA_TYPES.get(suffix)
    if media_type is None:
        raise ValueError(
            f"Unsupported file type '{suffix}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    if len(data) > MAX_IMAGE_BYTES:
        resized = _downscale_image(data, suffix)
        if resized is None:
            raise ValueError(
                f"{path.name} is {len(data) / 1_048_576:.1f} MB, above the 5 MB "
                "image limit. Install Pillow (pip install Pillow) to enable "
                "automatic downscaling, or resize the scan yourself."
            )
        warnings.append(
            f"Downscaled {path.name} from {len(data) / 1_048_576:.1f} MB to "
            f"{len(resized) / 1_048_576:.1f} MB to fit the 5 MB image limit."
        )
        data, media_type = resized, ("image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png")

    return (
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(data).decode("ascii"),
            },
        },
        warnings,
    )


def _build_instruction(context: str | None, language: str | None) -> str:
    parts = ["Transcribe this handwritten document."]
    if language:
        parts.append(f"The document is written in {language}.")
    if context:
        parts.append(f"Collection context: {context}")
    return " ".join(parts)


def transcribe_file(
    client: anthropic.Anthropic,
    path: Path,
    *,
    model: str = DEFAULT_MODEL,
    context: str | None = None,
    language: str | None = None,
    effort: str = "high",
    max_tokens: int = DEFAULT_MAX_TOKENS,
    as_json: bool = False,
    on_text=None,
) -> TranscriptionResult:
    """Transcribe one image or PDF.

    ``on_text`` is an optional callback receiving text deltas as they stream.
    """
    source_block, warnings = _build_source_block(path)

    request: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": effort},
        "system": [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [
            {
                "role": "user",
                "content": [
                    source_block,
                    {"type": "text", "text": _build_instruction(context, language)},
                ],
            }
        ],
    }
    if as_json:
        request["output_config"]["format"] = {
            "type": "json_schema",
            "schema": JSON_SCHEMA,
        }

    with client.messages.stream(**request) as stream:
        for delta in stream.text_stream:
            if on_text is not None:
                on_text(delta)
        message = stream.get_final_message()

    text = "".join(
        block.text for block in message.content if block.type == "text"
    ).strip()

    result = TranscriptionResult(
        source=path,
        text=text,
        model=message.model,
        stop_reason=message.stop_reason,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
        warnings=warnings,
    )
    if result.truncated:
        result.warnings.append(
            f"Output hit the {max_tokens}-token limit and may be incomplete; "
            "re-run with a higher --max-tokens."
        )
    return result
