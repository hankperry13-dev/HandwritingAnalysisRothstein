"""Command-line interface for the archival cursive transcriber."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic

from transcriber.core import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    SUPPORTED_SUFFIXES,
    transcribe_file,
)


def collect_inputs(paths: list[str]) -> list[Path]:
    """Expand the given files/directories into a sorted list of scan files."""
    files: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files.extend(
                child
                for child in sorted(p.iterdir())
                if child.suffix.lower() in SUPPORTED_SUFFIXES
            )
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(f"No such file or directory: {raw}")
    if not files:
        raise FileNotFoundError(
            "No supported files found. "
            f"Supported types: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    return files


def output_path_for(source: Path, output_dir: Path | None, as_json: bool) -> Path:
    suffix = ".transcript.json" if as_json else ".transcript.md"
    directory = output_dir if output_dir is not None else source.parent
    return directory / (source.stem + suffix)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcribe",
        description=(
            "Transcribe handwritten cursive documents (letters, diaries, "
            "ledgers) from scanned images or PDFs using the Claude API."
        ),
        epilog=(
            "Authentication: set the ANTHROPIC_API_KEY environment variable "
            "(or log in with `ant auth login`)."
        ),
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        metavar="FILE_OR_DIR",
        help="Scan files (.jpg, .png, .gif, .webp, .pdf) or directories of scans",
    )
    parser.add_argument(
        "--context",
        help=(
            "Background that helps with ambiguous readings, e.g. "
            "'1870s family letters from a farm in upstate New York'"
        ),
    )
    parser.add_argument(
        "--language",
        help="Language of the documents if not English",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON (transcription, uncertain readings, "
        "names/dates/places, legibility) instead of Markdown",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        help="Directory for transcript files (default: alongside each input)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print transcripts to stdout instead of writing files",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model ID (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        default="high",
        help="Reasoning effort; raise for badly degraded documents (default: high)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Output token limit per document (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Don't stream transcription text to the terminal while working",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        files = collect_inputs(args.inputs)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic()
    failures = 0

    for index, path in enumerate(files, start=1):
        print(f"[{index}/{len(files)}] {path}", file=sys.stderr)
        stream_to_terminal = not args.quiet and not args.stdout

        try:
            result = transcribe_file(
                client,
                path,
                model=args.model,
                context=args.context,
                language=args.language,
                effort=args.effort,
                max_tokens=args.max_tokens,
                as_json=args.json,
                on_text=(
                    (lambda t: print(t, end="", flush=True, file=sys.stderr))
                    if stream_to_terminal
                    else None
                ),
            )
        except anthropic.AuthenticationError:
            print(
                "error: invalid or missing API key. Set ANTHROPIC_API_KEY or "
                "run `ant auth login`.",
                file=sys.stderr,
            )
            return 1
        except anthropic.RateLimitError:
            print(
                f"error: rate limited while processing {path.name}; wait a "
                "minute and re-run (already-written transcripts are kept).",
                file=sys.stderr,
            )
            return 1
        except (anthropic.APIError, ValueError, OSError) as exc:
            print(f"error: {path.name}: {exc}", file=sys.stderr)
            failures += 1
            continue

        if stream_to_terminal:
            print(file=sys.stderr)
        for warning in result.warnings:
            print(f"warning: {warning}", file=sys.stderr)

        if args.stdout:
            if len(files) > 1:
                print(f"===== {path} =====")
            print(result.text)
        else:
            out = output_path_for(path, args.output_dir, args.json)
            out.write_text(result.text + "\n", encoding="utf-8")
            print(
                f"  -> {out}  "
                f"({result.input_tokens} in / {result.output_tokens} out tokens)",
                file=sys.stderr,
            )

    if failures:
        print(f"{failures} of {len(files)} file(s) failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
