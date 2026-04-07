#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

mkdir -p output

if [ ! -d .venv ]; then
  /usr/bin/python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

.venv/bin/python -m src.main
