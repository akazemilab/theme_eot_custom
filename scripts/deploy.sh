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

page() { curl -s --max-time 30 -H "Host: $1" http://127.0.0.1:8069/ || true; }

# Wait until each homepage renders as its website. The HTTP port answers
# before the database registry has loaded, so poll the real pages.
wait_for() {  # host website_id
    for _ in $(seq 1 45); do
        out=$(page "$1")
        if echo "$out" | grep -q "data-website-id=\"$2\""; then
            printf '%s' "$out"
            return 0
        fi
        sleep 2
    done
    return 1
}
echo "Waiting for Odoo to serve both websites"
W1=$(wait_for www.eot.ir 1) || { echo "!! www.eot.ir did not render website 1" >&2; exit 1; }
W3=$(wait_for www.sepehrtherapy.ir 3) || { echo "!! www.sepehrtherapy.ir did not render website 3" >&2; exit 1; }
echo "$W1" | grep -q 'name="eot-theme"' || { echo "!! theme marker missing on website 1" >&2; exit 1; }
if echo "$W3" | grep -q 'name="eot-theme"'; then
    echo "!! theme marker LEAKED to website 3" >&2
    exit 1
fi

echo "OK: $MODULE @ $TARGET deployed. Marker on website 1, absent on website 3."
echo "Check: http://odoo.innerquest.me/"
