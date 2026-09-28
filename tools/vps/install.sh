#!/usr/bin/env bash
# Install/refresh the eot toolkit on the VPS (95.38.234.86). Idempotent.
#   curl -s https://raw.githubusercontent.com/akazemilab/theme_eot_custom/main/tools/vps/install.sh | bash
set -euo pipefail
T=/root/eot-tools
mkdir -p "$T"
if [ -d "$T/repo/.git" ]; then git -C "$T/repo" fetch -q origin main && git -C "$T/repo" checkout -q -B main origin/main
else git clone -q --depth 50 -b main https://github.com/akazemilab/theme_eot_custom "$T/repo"; fi
[ -d "$T/venv" ] || python3 -m venv "$T/venv"
"$T/venv/bin/pip" install -q tinycss2 requests
chmod +x "$T/repo/tools/vps/eot"
ln -sf "$T/repo/tools/vps/eot" /usr/local/bin/eot
# Requires the SSH alias "eot-odoo-prod" (key /root/.ssh/eot_odoo_prod_ed25519) in /root/.ssh/config.
eot status
