#!/usr/bin/env bash
# Deploy a branch or commit of theme_eot_custom to eot_main.
#
#   usage: deploy.sh <branch|commit>
#
# Run as root on eot-odoo-prod. Stops odoo20, upgrades the module, starts
# odoo20, then checks that the theme marker is on website 1 and NOT on
# website 3. Exits non-zero on any upgrade error or failed check.
set -euo pipefail

REF="${1:?usage: deploy.sh <branch|commit>}"
MODULE=theme_eot_custom
REPO=/opt/odoo/themes/$MODULE
DB=eot_main
CONF=/etc/odoo20.conf
ODOO_BIN=/opt/odoo/odoo/odoo-bin
PY=/opt/odoo/venv/bin/python3
SERVICE=odoo20
LOG_DIR=/var/log/odoo
TS=$(date +%Y%m%d-%H%M%S)
UPGRADE_LOG=$LOG_DIR/deploy-$MODULE-$TS.log

cd "$REPO"
git fetch --prune origin

if git rev-parse --verify --quiet "origin/$REF^{commit}" >/dev/null; then
    TARGET=$(git rev-parse "origin/$REF^{commit}")
elif git rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
    TARGET=$(git rev-parse "$REF^{commit}")
else
    echo "Unknown ref: $REF" >&2
    exit 1
fi

PREVIOUS=$(git rev-parse HEAD)
git checkout --quiet --detach "$TARGET"
echo "Checked out $TARGET ($REF), previous was $PREVIOUS"

echo "Stopping $SERVICE"
systemctl stop "$SERVICE"

echo "Upgrading $MODULE on $DB (log: $UPGRADE_LOG)"
set +e
sudo -u odoo "$PY" "$ODOO_BIN" -c "$CONF" -d "$DB" -u "$MODULE" \
    --stop-after-init --no-http >"$UPGRADE_LOG" 2>&1
RC=$?
set -e

echo "Starting $SERVICE"
systemctl start "$SERVICE"

if [ $RC -ne 0 ] || grep -qE ' (ERROR|CRITICAL) ' "$UPGRADE_LOG"; then
    echo "!! Upgrade reported errors (exit $RC):" >&2
    grep -nE ' (ERROR|CRITICAL|WARNING) |Traceback' "$UPGRADE_LOG" >&2 || true
    echo "!! To roll back: $0 $PREVIOUS" >&2
    exit 1
fi
grep -nE ' WARNING ' "$UPGRADE_LOG" || echo "No warnings during upgrade."

echo "Waiting for Odoo to answer"
for _ in $(seq 1 30); do
    code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8069/web/login || true)
    [ "$code" = 200 ] && break
    sleep 2
done
[ "$code" = 200 ] || { echo "!! Odoo not answering (last code $code)" >&2; exit 1; }

page() { curl -s --max-time 30 -H "Host: $1" http://127.0.0.1:8069/; }
W1=$(page www.eot.ir)
W3=$(page www.sepehrtherapy.ir)

echo "$W1" | grep -q 'data-website-id="1"' || { echo "!! www.eot.ir did not render website 1" >&2; exit 1; }
echo "$W3" | grep -q 'data-website-id="3"' || { echo "!! www.sepehrtherapy.ir did not render website 3" >&2; exit 1; }
echo "$W1" | grep -q 'name="eot-theme"' || { echo "!! theme marker missing on website 1" >&2; exit 1; }
if echo "$W3" | grep -q 'name="eot-theme"'; then
    echo "!! theme marker LEAKED to website 3" >&2
    exit 1
fi

echo "OK: $MODULE @ $TARGET deployed. Marker on website 1, absent on website 3."
echo "Check: http://odoo.innerquest.me/"
