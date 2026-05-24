#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo ""
echo "Setup complete. System dependencies required (Arch/CachyOS):"
echo "  sudo pacman -S wl-clipboard libayatana-appindicator"
echo ""
echo "For global hotkeys, ensure your user is in the 'input' group:"
echo "  sudo usermod -aG input \$USER   (then re-login)"
echo ""
echo "Run the app with: bash scripts/run.sh"
