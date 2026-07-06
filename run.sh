#!/usr/bin/env bash
# One-command launcher for the archival cursive transcriber (macOS / Linux).
#
#   ./run.sh letter.jpg                     transcribe one scan (Claude engine)
#   ./run.sh scans/ -o transcripts/         transcribe a whole folder
#   ./run.sh letter.jpg --engine local      no-API-key mode (local model)
#
# The first run sets everything up automatically: it creates a private Python
# environment in .venv/, installs the dependencies, and (for the Claude
# engine) asks once for your API key and remembers it in a local .env file.

set -euo pipefail
cd "$(dirname "$0")"

# --- find Python -------------------------------------------------------------
PY=python3
command -v "$PY" >/dev/null 2>&1 || PY=python
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "error: Python 3 is not installed. Get it from https://www.python.org/downloads/" >&2
    exit 1
fi

# --- one-time environment setup ----------------------------------------------
if [ ! -d .venv ]; then
    echo "First run: creating a private Python environment (one time only)..."
    "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import anthropic" >/dev/null 2>&1; then
    echo "Installing dependencies (one time only)..."
    pip install --quiet -r requirements.txt
fi

# --- no arguments: show examples and stop --------------------------------------
if [ "$#" -eq 0 ]; then
    echo "Setup is done. Now tell it what to transcribe:"
    echo
    echo "  ./run.sh letter.jpg                     one scan"
    echo "  ./run.sh scans/ -o transcripts/         a whole folder"
    echo "  ./run.sh letter.jpg --engine local      without an API key"
    echo "  ./run.sh --help                         all options"
    exit 0
fi

# --- inspect arguments ----------------------------------------------------------
use_local=0
wants_help=0
prev=""
for arg in "$@"; do
    if { [ "$prev" = "--engine" ] && [ "$arg" = "local" ]; } || [ "$arg" = "--engine=local" ]; then
        use_local=1
    fi
    if [ "$arg" = "--help" ] || [ "$arg" = "-h" ]; then
        wants_help=1
    fi
    prev="$arg"
done
if [ "$use_local" = "1" ] && ! python -c "import torch, transformers" >/dev/null 2>&1; then
    echo "Installing local-engine dependencies (one time only, ~1-2 GB)..."
    pip install --quiet -r requirements-local.txt
fi

# --- API key (Claude engine only; not needed for --help) ------------------------
if [ "$use_local" = "0" ] && [ "$wants_help" = "0" ]; then
    if [ -z "${ANTHROPIC_API_KEY:-}" ] && [ -f .env ]; then
        # shellcheck disable=SC1091
        set -a; source .env; set +a
    fi
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        echo
        echo "The Claude engine needs an Anthropic API key (create one at"
        echo "https://console.anthropic.com/ under 'API Keys')."
        echo "It will be remembered in the local .env file for next time."
        echo "Tip: to skip API keys entirely, use:  ./run.sh <file> --engine local"
        echo
        read -r -p "Paste your API key (sk-ant-...): " ANTHROPIC_API_KEY
        if [ -z "$ANTHROPIC_API_KEY" ]; then
            echo "error: no key entered." >&2
            exit 1
        fi
        export ANTHROPIC_API_KEY
        printf 'ANTHROPIC_API_KEY=%s\n' "$ANTHROPIC_API_KEY" > .env
        chmod 600 .env
        echo "Saved to .env (kept out of git)."
    fi
fi

# --- run -----------------------------------------------------------------------
exec python -m transcriber "$@"
