"""Local, no-API-key transcription engine built on TrOCR.

Runs entirely on your machine: a one-time model download from Hugging Face,
then fully offline. Pages are split into text lines with a projection-profile
segmenter (numpy only), and each line is recognized with a TrOCR
vision-encoder/decoder model.

Heavy dependencies (torch, transformers) are imported lazily so the Claude
engine works without them installed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from transcriber.core import IMAGE_MEDIA_TYPES, TranscriptionResult

DEFAULT_LOCAL_MODEL = "microsoft/trocr-base-handwritten"

# Lines whose mean token probability falls below this get flagged for review.
LOW_CONFIDENCE = 0.60

_INSTALL_HINT = (
    "Local mode needs extra packages. Install them with:\n"
    "    pip install -r requirements-local.txt\n"
    "(torch, transformers, Pillow, numpy)"
)


@dataclass
class RecognizedLine:
    text: str
    confidence: float


def _import_deps():
    try:
        import numpy as np
        import torch
        from PIL import Image
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError as exc:
        raise RuntimeError(f"{_INSTALL_HINT}\n(missing: {exc.name})") from exc
    return np, torch, Image, TrOCRProcessor, VisionEncoderDecoderModel


def _otsu_threshold(gray, np) -> int:
    """Otsu's method on a uint8 grayscale array (no OpenCV needed)."""
    hist, _ = np.histogram(gray, bins=256, range=(0, 256))
    total = gray.size
    sum_all = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0
    best_var = -1.0
    threshold = 127
    for t in range(256):
        w_b += int(hist[t])
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += t * int(hist[t])
        m_b = sum_b / w_b
        m_f = (sum_all - sum_b) / w_f
        var = w_b * w_f * (m_b - m_f) ** 2
        if var > best_var:
            best_var, threshold = var, t
    return threshold


def segment_lines(page_image, np):
    """Split a page image into line images using a horizontal projection profile.

    Returns a list of PIL images, top to bottom. Falls back to the whole page
    as a single "line" if nothing can be segmented.
    """
    gray = np.asarray(page_image.convert("L"), dtype=np.uint8)
    height, width = gray.shape
    # <= because Otsu returns the last bin belonging to the darker (ink) class
    ink = gray <= _otsu_threshold(gray, np)

    profile = ink.sum(axis=1).astype(float)
    # Smooth so gaps inside letterforms don't split a line in two.
    kernel = max(3, height // 300)
    profile = np.convolve(profile, np.ones(kernel) / kernel, mode="same")

    noise_floor = max(2.0, 0.005 * width)
    active = profile > noise_floor

    # Collect contiguous runs of active rows.
    runs: list[list[int]] = []
    start = None
    for row, is_active in enumerate(active):
        if is_active and start is None:
            start = row
        elif not is_active and start is not None:
            runs.append([start, row])
            start = None
    if start is not None:
        runs.append([start, height])

    if not runs:
        return [page_image]

    # Merge runs separated by gaps smaller than half the median line height —
    # those are usually ascenders/descenders split from their line.
    heights = [b - a for a, b in runs]
    median_height = sorted(heights)[len(heights) // 2]
    merged = [runs[0]]
    for a, b in runs[1:]:
        if a - merged[-1][1] < median_height * 0.5:
            merged[-1][1] = b
        else:
            merged.append([a, b])

    # Drop specks (stains, edge shadows) shorter than a third of a typical line.
    merged = [(a, b) for a, b in merged if (b - a) >= max(6, median_height / 3)]
    if not merged:
        return [page_image]

    lines = []
    for a, b in merged:
        pad = max(2, (b - a) // 4)
        top = max(0, a - pad)
        bottom = min(height, b + pad)
        # Trim columns to the inked region so the model sees mostly writing.
        cols = ink[top:bottom].any(axis=0)
        col_idx = np.flatnonzero(cols)
        if len(col_idx) == 0:
            continue
        left = max(0, int(col_idx[0]) - pad)
        right = min(width, int(col_idx[-1]) + pad)
        lines.append(page_image.crop((left, top, right, bottom)))

    return lines or [page_image]


class LocalTranscriber:
    """Loads TrOCR once and transcribes any number of files with it."""

    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL, device: str | None = None):
        np, torch, Image, TrOCRProcessor, VisionEncoderDecoderModel = _import_deps()
        self._np = np
        self._torch = torch
        self._Image = Image
        self.model_name = model_name
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = TrOCRProcessor.from_pretrained(model_name)
        self.model = VisionEncoderDecoderModel.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()

    def _load_pages(self, path: Path):
        suffix = path.suffix.lower()
        if suffix in IMAGE_MEDIA_TYPES:
            return [self._Image.open(path)]
        if suffix == ".pdf":
            try:
                import pypdfium2 as pdfium
            except ImportError as exc:
                raise RuntimeError(
                    "PDF input in local mode needs pypdfium2 "
                    "(pip install pypdfium2), or export the pages as images."
                ) from exc
            pdf = pdfium.PdfDocument(str(path))
            try:
                return [
                    page.render(scale=300 / 72).to_pil() for page in pdf
                ]
            finally:
                pdf.close()
        raise ValueError(
            f"Unsupported file type '{suffix}' for local mode. "
            f"Supported: {', '.join(sorted(IMAGE_MEDIA_TYPES))}, .pdf"
        )

    def _recognize(self, line_images, batch_size: int = 8) -> list[RecognizedLine]:
        torch = self._torch
        results: list[RecognizedLine] = []
        for i in range(0, len(line_images), batch_size):
            batch = [img.convert("RGB") for img in line_images[i : i + batch_size]]
            pixel_values = self.processor(images=batch, return_tensors="pt").pixel_values
            pixel_values = pixel_values.to(self.device)
            with torch.no_grad():
                out = self.model.generate(
                    pixel_values,
                    max_new_tokens=128,
                    output_scores=True,
                    return_dict_in_generate=True,
                )
            texts = self.processor.batch_decode(out.sequences, skip_special_tokens=True)
            scores = self.model.compute_transition_scores(
                out.sequences, out.scores, normalize_logits=True
            )
            for text, token_scores in zip(texts, scores):
                finite = token_scores[torch.isfinite(token_scores)]
                confidence = float(finite.exp().mean()) if len(finite) else 0.0
                results.append(RecognizedLine(text.strip(), confidence))
        return results

    def transcribe_file(
        self,
        path: Path,
        *,
        as_json: bool = False,
        on_text=None,
    ) -> TranscriptionResult:
        pages = self._load_pages(path)
        page_results: list[list[RecognizedLine]] = []
        warnings: list[str] = []

        for page in pages:
            lines = segment_lines(page, self._np)
            recognized = [r for r in self._recognize(lines) if r.text]
            page_results.append(recognized)
            if on_text is not None:
                for line in recognized:
                    on_text(line.text + "\n")

        all_lines = [line for page in page_results for line in page]
        low_confidence = sum(1 for l in all_lines if l.confidence < LOW_CONFIDENCE)
        if not all_lines:
            warnings.append(
                f"No text lines detected in {path.name} — the scan may be too "
                "faint for the local segmenter. Try increasing contrast, or "
                "use the Claude engine."
            )

        if as_json:
            text = json.dumps(
                {
                    "source": str(path),
                    "engine": "local",
                    "model": self.model_name,
                    "transcription": "\n\n".join(
                        "\n".join(l.text for l in page) for page in page_results
                    ),
                    "lines": [
                        {"text": l.text, "confidence": round(l.confidence, 3)}
                        for l in all_lines
                    ],
                    "low_confidence_lines": low_confidence,
                },
                indent=2,
                ensure_ascii=False,
            )
        else:
            body_parts = []
            for number, page in enumerate(page_results, start=1):
                if len(page_results) > 1:
                    body_parts.append(f"[page {number}]")
                body_parts.append(
                    "\n".join(
                        l.text + ("  `[low confidence]`" if l.confidence < LOW_CONFIDENCE else "")
                        for l in page
                    )
                )
            body = "\n\n".join(body_parts)
            text = (
                "## Transcription\n\n"
                f"{body}\n\n"
                "## Notes\n\n"
                f"- Engine: local ({self.model_name}), no API used\n"
                f"- {len(all_lines)} line(s) recognized across {len(pages)} page(s); "
                f"{low_confidence} flagged `[low confidence]`\n"
                "- Local recognition is markedly less accurate than the Claude "
                "engine on degraded or historical cursive — proofread against "
                "the original scan."
            )

        return TranscriptionResult(
            source=path,
            text=text,
            model=self.model_name,
            stop_reason=None,
            warnings=warnings,
        )
