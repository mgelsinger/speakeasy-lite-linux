#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .venv/bin/python ]]; then
    echo "No venv found. Run: bash scripts/setup.sh" >&2
    exit 1
fi

.venv/bin/python app/main.py
