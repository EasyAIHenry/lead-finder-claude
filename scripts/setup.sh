#!/usr/bin/env bash
# Makes .venv on Python 3.12 or newer and installs everything the lead finder needs.
# ScrapeGraphAI 2.x needs Python 3.12+. On older Python, pip quietly installs the old 1.x instead,
# so this script refuses to continue rather than give you a broken install.
set -euo pipefail
cd "$(dirname "$0")/.."

ok() { "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; }

if command -v uv >/dev/null 2>&1; then
  echo "Using uv to make .venv on Python 3.12"
  uv venv --python 3.12 .venv
  uv pip install --python .venv/bin/python -r requirements.txt
else
  PY=""
  for c in python3.14 python3.13 python3.12 /opt/homebrew/bin/python3.14 /opt/homebrew/bin/python3.13 \
           /opt/homebrew/bin/python3.12 /usr/local/bin/python3.12 python3; do
    if command -v "$c" >/dev/null 2>&1 && ok "$c"; then PY="$c"; break; fi
  done
  if [ -z "$PY" ]; then
    found="$(python3 --version 2>/dev/null || echo 'no python3')"
    echo "Stopped: the lead finder needs Python 3.12 or newer, and this computer has: $found."
    echo "Install one of these, then run this script again:"
    echo "  uv (recommended):   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  Homebrew Python:    brew install python@3.12"
    exit 1
  fi
  echo "Using $PY ($("$PY" --version)) to make .venv"
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install -r requirements.txt
fi

if ! ok .venv/bin/python; then
  echo "Stopped: .venv is not on Python 3.12+. Delete the .venv folder and run this script again."
  exit 1
fi

echo "Installing the hidden browser ScrapeGraphAI uses (Playwright Chromium)"
.venv/bin/python -m playwright install chromium

v="$(.venv/bin/python -c 'import importlib.metadata as m; print(m.version("scrapegraphai"))')"
echo "Done. ScrapeGraphAI $v on $(.venv/bin/python --version)."
if command -v ollama >/dev/null 2>&1; then
  echo "Next: ollama pull qwen2.5:7b-instruct   (once, 4.7 GB)"
else
  echo "Next: install Ollama from https://ollama.com, open it, then: ollama pull qwen2.5:7b-instruct"
fi
echo "Then: cp config.example.yaml config.yaml, edit it, and run: .venv/bin/python lead_finder.py --max 3"
