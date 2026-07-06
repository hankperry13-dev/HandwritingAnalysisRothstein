# Archival Cursive Transcriber

A command-line tool that transcribes handwritten cursive documents — letters,
diaries, ledgers, deeds, meeting minutes — from scanned images or PDFs.

Two engines are available:

- **Claude engine** (default) — uses the Claude API's vision capabilities.
  Most accurate on degraded archival material; requires an API key.
- **Local engine** (`--engine local`) — runs Microsoft's open-source TrOCR
  model on your own machine. **No API key, no account, free**, and works
  offline after a one-time model download. Less accurate on difficult
  material — see [No-API-key mode](#no-api-key-mode-local-engine).

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

## Installation

### Step 1 — Check your Python version

The tool requires **Python 3.10 or newer**. Check what you have:

```bash
python3 --version
```

If that prints `Python 3.10.x` or higher, you're good. If the command isn't
found or the version is older, install Python from
[python.org/downloads](https://www.python.org/downloads/) (macOS/Windows) or
your package manager (Linux, e.g. `sudo apt install python3 python3-venv python3-pip`).

> On Windows, the command may be `python` or `py` instead of `python3` — use
> whichever works in the steps below.

### Step 2 — Get the code

If you haven't already cloned this repository:

```bash
git clone https://github.com/hankperry13-dev/HandwritingAnalysisRothstein.git
cd HandwritingAnalysisRothstein
```

(Or download it as a ZIP from GitHub and unzip it, then `cd` into the folder.)

### Step 3 — Create and activate a virtual environment (recommended)

This keeps the tool's dependencies separate from the rest of your system:

```bash
python3 -m venv .venv
```

Then activate it — this differs by operating system:

| OS / shell | Command |
|---|---|
| macOS / Linux | `source .venv/bin/activate` |
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (cmd.exe) | `.venv\Scripts\activate.bat` |

You'll know it worked when your prompt shows `(.venv)` at the start. You'll
need to re-activate it in each new terminal session before using the tool.

### Step 4 — Install the dependencies

With the virtual environment active:

```bash
pip install -r requirements.txt
```

This installs two packages:

- `anthropic` — the Claude API client (required)
- `Pillow` — image handling, used to automatically shrink scans that are over
  the 5 MB API limit (optional but recommended)

### Step 5 — Get and set your Anthropic API key

The tool calls the Claude API, which requires an API key:

1. Sign up or log in at [console.anthropic.com](https://console.anthropic.com/)
2. Go to **API Keys** and click **Create Key**
3. Copy the key (it starts with `sk-ant-`) — it's shown only once

Then make the key available to the tool:

**macOS / Linux:**

```bash
export ANTHROPIC_API_KEY=sk-ant-your-key-here
```

This lasts for the current terminal session. To make it permanent, add that
line to your shell profile (`~/.zshrc` on modern macOS, `~/.bashrc` on most
Linux systems), then open a new terminal.

**Windows (PowerShell):**

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"       # current session only
setx ANTHROPIC_API_KEY "sk-ant-your-key-here"          # permanent (new terminals)
```

> Treat the key like a password: don't commit it to git or paste it into
> shared documents. Note that API usage is billed per token — a typical
> single-page letter costs a few cents to transcribe.

### Step 6 — Verify the installation

```bash
python -m transcriber --help
```

If you see the usage text with the list of options, everything is installed
correctly. Then do a real end-to-end check with one scan:

```bash
python -m transcriber path/to/some-letter.jpg --stdout
```

You should see the transcription stream into your terminal.

### Optional — install as a `transcribe` command

If you'd rather type `transcribe letter.jpg` than `python -m transcriber letter.jpg`:

```bash
pip install -e .
```

### Troubleshooting

| Symptom | Fix |
|---|---|
| `python3: command not found` | Install Python (Step 1); on Windows try `python` or `py` |
| `No module named anthropic` | The virtual environment isn't active (Step 3) or dependencies weren't installed (Step 4) |
| `error: invalid or missing API key` | The `ANTHROPIC_API_KEY` variable isn't set in *this* terminal session (Step 5) — `echo $ANTHROPIC_API_KEY` (macOS/Linux) or `echo $env:ANTHROPIC_API_KEY` (PowerShell) should print your key. Or skip keys entirely with `--engine local` (see below). |
| `Local mode needs extra packages` | Install them: `pip install -r requirements-local.txt` |
| `... is above the 5 MB image limit` | Install Pillow (`pip install Pillow`) to enable automatic downscaling, or resize the scan |
| `error: rate limited` | You've hit your API tier's request limit — wait a minute and re-run; finished transcripts are kept |

## No-API-key mode (local engine)

If you can't (or don't want to) use an API key, the tool has a second engine
that runs entirely on your own machine using Microsoft's open-source
**TrOCR** handwriting-recognition model. Nothing is sent to any service and
no account is needed — the only network access is a one-time model download
from Hugging Face; after that it works fully offline.

**Set expectations first:** TrOCR was trained on modern English handwriting.
On clean, well-scanned material it does a reasonable job, but on faded ink,
damaged paper, historical letterforms, and non-English documents it is
**markedly less accurate** than the Claude engine. Lines the model is unsure
about are flagged `[low confidence]` in the output — always proofread against
the original scan.

### Local mode installation

Follow Steps 1–3 of the installation above (Python, code, virtual
environment) — then instead of Steps 4–5:

1. Install the local-engine dependencies (~1–2 GB, mostly PyTorch):

   ```bash
   pip install -r requirements-local.txt
   ```

   On a machine without an NVIDIA GPU you can install the much smaller
   CPU-only PyTorch first:

   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install -r requirements-local.txt
   ```

2. There is no Step 5 — no API key is needed.

3. Verify:

   ```bash
   python -m transcriber path/to/letter.jpg --engine local --stdout
   ```

   The first run downloads the model (~350 MB) and caches it under
   `~/.cache/huggingface/`; later runs work offline.

### Local mode usage

Everything works the same — just add `--engine local`:

```bash
python -m transcriber scans/ --engine local -o transcripts/
python -m transcriber ledger.png --engine local --json   # per-line confidences
```

For better accuracy at the cost of a bigger download (~2.4 GB) and slower
runs, use the large model:

```bash
python -m transcriber scans/ --engine local \
  --local-model microsoft/trocr-large-handwritten
```

Notes and limits of local mode:

- `--context`, `--language`, and `--effort` only apply to the Claude engine
  and are ignored locally.
- PDF input additionally needs `pypdfium2` (included in
  `requirements-local.txt`).
- Pages are split into lines automatically; if a scan is very faint or
  skewed, the segmenter may miss lines — increasing scan contrast helps.
- JSON output in local mode reports a confidence score per line instead of
  the Claude engine's uncertain-reading analysis.

## Which engine should I use?

| | Claude engine (default) | Local engine (`--engine local`) |
|---|---|---|
| API key / account | Required | None |
| Cost | ~cents per page | Free |
| Works offline | No | Yes (after model download) |
| Degraded/historical cursive | Strong | Weak-to-fair |
| Uncertainty marking | `[word?]`, `[illegible]`, alternatives with reasons | `[low confidence]` per line |
| Marginalia, crossed-out text, notes section | Yes | No |
| Speed | ~10–60 s per page | Seconds (GPU) to ~1 min (CPU) per page |

A practical workflow for large collections: run everything through the local
engine for a free first pass, then re-run the important or hard-to-read
documents through the Claude engine.

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
