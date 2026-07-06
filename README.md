# Archival Cursive Transcriber

A command-line tool that transcribes handwritten cursive documents — letters,
diaries, ledgers, deeds, meeting minutes — from scanned images or PDFs, using
the Claude API's vision capabilities.

It is built for archival material: faded ink, bleed-through, stained or
damaged paper, historical letterforms, and marginalia. Transcripts follow
standard paleography conventions so uncertainty is always visible:

- `[word?]` — uncertain reading (`[word1?/word2?]` when two are plausible)
- `[illegible]` / `[3 words illegible]` — unreadable text
- `[crossed out: ...]`, `[inserted: ...]`, `[in margin: ...]` — author edits
- Original spelling, punctuation, line breaks, and abbreviations are preserved
  (never silently modernized)

Each transcript ends with a **Notes** section summarizing legibility, dates,
names, places, and the most significant uncertain readings — useful for
cataloging.

## Setup

Requires Python 3.10+.

```bash
pip install -r requirements.txt      # anthropic + optional Pillow
export ANTHROPIC_API_KEY=sk-ant-...  # or `ant auth login`
```

Optionally install as a command:

```bash
pip install -e .                      # provides the `transcribe` command
```

## Usage

Transcribe a single scan (transcript is written next to the input as
`letter.transcript.md`):

```bash
python -m transcriber letter.jpg
```

Batch-transcribe a folder of scans into a `transcripts/` directory, with
collection context to help resolve ambiguous readings:

```bash
python -m transcriber scans/ \
  --output-dir transcripts/ \
  --context "1870s family letters from a farm in upstate New York"
```

Multi-page PDFs work directly:

```bash
python -m transcriber diary_1893.pdf
```

Structured output for building an index or database:

```bash
python -m transcriber ledger_p12.png --json
```

The JSON includes the transcription plus `uncertain_readings` (with
alternatives and reasons), `dates_mentioned`, `people_mentioned`,
`places_mentioned`, and an overall `legibility` rating.

### Options

| Flag | Purpose |
|---|---|
| `--context "..."` | Background about the collection (era, region, subject) — improves ambiguous readings |
| `--language ...` | Document language if not English |
| `--json` | Structured JSON output instead of Markdown |
| `--output-dir DIR`, `-o` | Where to write transcripts (default: next to each input) |
| `--stdout` | Print transcripts instead of writing files |
| `--effort {low,medium,high,xhigh,max}` | Reasoning effort; raise for badly degraded documents (default: `high`) |
| `--model ID` | Claude model (default: `claude-opus-4-8`) |
| `--max-tokens N` | Output limit per document (default: 32000) |
| `--quiet`, `-q` | Don't stream text to the terminal while working |

## Tips for best results

- **Scan quality matters most.** Aim for at least 300 DPI. The tool
  automatically downscales scans over 5 MB (requires Pillow) — detail above
  ~2576 px on the long edge doesn't improve accuracy.
- **Give context.** `--context` with the era, region, and likely names is the
  single biggest accuracy lever for ambiguous words and proper nouns.
- **Raise effort for hard material.** `--effort xhigh` or `max` helps with
  badly faded ink, cross-writing, or unfamiliar hands.
- **Review the Notes section.** Uncertain readings are flagged there so a
  human can verify them against the original — the model is instructed never
  to invent text, but transcription of degraded cursive should always be
  spot-checked.

## Supported input types

`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.pdf` (PDFs up to 100 pages).
