#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Ensure venv exists
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

# Activate venv
source .venv/bin/activate

# Install deps if requirements exists
if [ -f requirements.txt ]; then
  pip install -U pip setuptools wheel
  pip install -r requirements.txt
fi

# Basic syntax checks (non-fatal)
if [ -f watcher_linux.py ]; then
  python -m py_compile watcher_linux.py || true
fi
if [ -f curator_core.py ]; then
  python -m py_compile curator_core.py || true
fi

exit 0
