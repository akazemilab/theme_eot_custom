#!/usr/bin/env bash
# Rehearse a theme ref on a disposable clone of eot_main (CLAUDE.md pitfall #15):
# restore the latest backup into a scratch DB, upgrade the module from a
# worktree, optionally run a cleanup script (dry then real), serve on :8070.
# Generalized from the milestone-6 version (was hardcoded to eot_m6test /
# m6_cleanup.py) so later milestones can reuse it without editing the script.
#
#   usage: rehearse.sh [git-ref] [db-name] [cleanup-script-relative-to-repo]
#   examples:
#     rehearse.sh origin/milestone/07-foo                # no cleanup step
#     rehearse.sh origin/milestone/07-foo eot_m7test scripts/m7_cleanup.py
#
# Run detached as root on eot-odoo-prod (this restores a DB and starts an
# Odoo process; it does not touch eot_main).
set -uo pipefail
WT=/opt/odoo/rehearse_wt; FS=/opt/odoo/.local/share/Odoo/filestore
PY=/opt/odoo/venv/bin/python3; BIN=/opt/odoo/odoo/odoo-bin
AP=$WT,/opt/odoo/enterprise,/opt/odoo/odoo/addons
REF=${1:-origin/main}
DB=${2:-eot_rehearse_test}
CLEANUP=${3:-}
step(){ echo "=== $(date +%T) $*"; }

step reset
# Bracket the pattern ("[-]d $DB" not "d $DB"): over ssh this whole line is
# itself the remote command, so an unbracketed pkill -f matches its own
# argv and can kill the invoking shell instead of the target (CLAUDE.md
# "pkill -f / pgrep -f self-match" pitfall). dropdb --force (PG13+) already
# terminates other connections, so this is just a courtesy stop.
pkill -f "[-]d $DB" 2>/dev/null; sleep 1
sudo -u postgres dropdb --if-exists --force "$DB"
rm -rf "$FS/$DB"

step restore
sudo -u postgres createdb -O odoo "$DB"
LATEST_DUMP=$(ls -t /var/backups/odoo/eot_main_pre_*.dump 2>/dev/null | head -1)
[ -z "$LATEST_DUMP" ] && { echo "no eot_main_pre_*.dump backup found in /var/backups/odoo - take one first (pg_dump -Fc) before rehearsing"; exit 1; }
sudo -u postgres pg_restore -d "$DB" --no-owner --role=odoo -j 4 "$LATEST_DUMP" 2>&1 | grep -v "^$" | tail -3
cp -a "$FS/eot_main" "$FS/$DB"

step worktree
cd /opt/odoo/themes/theme_eot_custom && git fetch -q --prune origin
rm -rf "$WT"; mkdir -p "$WT"
git worktree prune; git worktree add -f --detach "$WT/theme_eot_custom" "$REF" >/dev/null 2>&1 || cp -a . "$WT/theme_eot_custom"
( cd "$WT/theme_eot_custom" && git checkout -q --detach "$REF" && git log --oneline -1 )
chown -R odoo:odoo "$WT"

step scss
$PY -c "
import sass, glob
for f in glob.glob('$WT/theme_eot_custom/static/src/scss/*.scss'):
    css = sass.compile(filename=f, output_style='compressed')
    print('scss ok', f.split('/')[-1], len(css), 'bytes')
" 2>&1 | tail -6

step upgrade
sudo -u odoo $PY $BIN -c /etc/odoo20.conf -d "$DB" --db-filter="^$DB\$" --addons-path=$AP -u theme_eot_custom --stop-after-init --no-http > /tmp/rehearse_upgrade.log 2>&1
echo "rc=$?"; grep -E " (ERROR|CRITICAL|WARNING) |Traceback|ParseError" /tmp/rehearse_upgrade.log | cut -c1-300 | head -15

CLEANUP_PATH="$WT/theme_eot_custom/$CLEANUP"
if [ -n "$CLEANUP" ] && [ -f "$CLEANUP_PATH" ]; then
    # CLAUDE.md pitfall #19: must run as the odoo user with its OWN HOME, never `sudo -E`.
    step cleanup-dry
    sudo -u odoo env HOME=/opt/odoo EOT_DRY_RUN=1 $PY $BIN shell -c /etc/odoo20.conf -d "$DB" --db-filter="^$DB\$" --addons-path=$AP --no-http < "$CLEANUP_PATH" 2>&1 | grep -vE "^(20[0-9]{2}-| *$|>>>|\.\.\.)" | tail -20
    step cleanup
    sudo -u odoo env HOME=/opt/odoo $PY $BIN shell -c /etc/odoo20.conf -d "$DB" --db-filter="^$DB\$" --addons-path=$AP --no-http < "$CLEANUP_PATH" 2>&1 | grep -vE "^(20[0-9]{2}-| *$|>>>|\.\.\.)" | tail -20
else
    step cleanup-skipped
    [ -n "$CLEANUP" ] && echo "cleanup script not found at $CLEANUP_PATH - skipping"
fi

step serve
sudo -u odoo setsid nohup $PY $BIN -c /etc/odoo20.conf -d "$DB" --db-filter="^$DB\$" --addons-path=$AP --http-port=8070 --workers=0 --max-cron-threads=0 --no-database-list > /tmp/rehearse_serve.log 2>&1 &
for i in $(seq 1 60); do curl -s -o /dev/null -H "Host: www.eot.ir" http://127.0.0.1:8070/web/login && break; sleep 2; done
step ready
echo "serving $DB on :8070 - curl every route/redirect/sitemap edge case now, then dropdb --force $DB and rm -rf $FS/$DB when done"
