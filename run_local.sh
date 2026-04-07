#!/usr/bin/env bash
# Quick local test — no Docker needed.
# Requires: Python 3.11+, Ollama running or installable
# Usage: ./run_local.sh [--dry-run]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f .env ]; then
  echo "Error: .env not found. Copy .env.example and fill in UNSPLASH_ACCESS_KEY."
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating virtualenv..."
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

python -m src.main "$@"
