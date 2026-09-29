#!/usr/bin/env bash
# Install/refresh the eot toolkit on the VPS (95.38.234.86). Idempotent.
#   curl -s https://raw.githubusercontent.com/akazemilab/theme_eot_custom/main/tools/vps/install.sh | bash
#   bash install.sh --browser     # also the headless browser for `eot audit`
#
# Network from this VPS (Iranian IP): files.pythonhosted.org does not resolve,
# cdn.playwright.dev and storage.googleapis.com answer 403 "not available in
# your location". What works: the runflare PyPI mirror, apt, snapcraft, npm,
# github. So pip uses the mirror and Chromium comes from snap.
set -euo pipefail
PIP_MIRROR=https://mirror-pypi.runflare.com/simple
T=/root/eot-tools
mkdir -p "$T"
if [ -d "$T/repo/.git" ]; then git -C "$T/repo" fetch -q origin main && git -C "$T/repo" checkout -q -B main origin/main
else git clone -q --depth 50 -b main https://github.com/akazemilab/theme_eot_custom "$T/repo"; fi
[ -d "$T/venv" ] || python3 -m venv "$T/venv"
"$T/venv/bin/pip" install -q -i "$PIP_MIRROR" tinycss2 requests
chmod +x "$T/repo/tools/vps/eot"
ln -sf "$T/repo/tools/vps/eot" /usr/local/bin/eot

if [ "${1:-}" = "--browser" ]; then
  B=/root/eot-browser
  mkdir -p "$B"
  [ -d "$B/venv" ] || python3 -m venv "$B/venv"
  "$B/venv/bin/pip" install -q -i "$PIP_MIRROR" playwright
  "$B/venv/bin/python" -m playwright install-deps chromium   # system libs via apt (works)
  snap list chromium >/dev/null 2>&1 || snap install chromium # the browser itself (CDN is geo-blocked)
  echo "browser: /snap/chromium/current/usr/lib/chromium-browser/chrome"
fi
# Requires the SSH alias "eot-odoo-prod" (key /root/.ssh/eot_odoo_prod_ed25519) in /root/.ssh/config.
eot status
