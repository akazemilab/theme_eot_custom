#!/usr/bin/env bash
# Rehearse a theme ref on a disposable clone of eot_main (CLAUDE.md pitfall #15):
# restore the latest backup into eot_m6test, upgrade the module from a
# worktree, run scripts/m6_cleanup.py (dry then real), serve on :8070.
#   usage: rehearse.sh [git-ref]   (run detached as root on eot-odoo-prod)
set -uo pipefail
DB=eot_m6test; WT=/opt/odoo/m6wt; FS=/opt/odoo/.local/share/Odoo/filestore
PY=/opt/odoo/venv/bin/python3; BIN=/opt/odoo/odoo/odoo-bin
AP=$WT,/opt/odoo/enterprise,/opt/odoo/odoo/addons
REF=${1:-origin/milestone/06-inner-pages}
step(){ echo "=== $(date +%T) $*"; }
step reset
pkill -f "d $DB" 2>/dev/null; sleep 1
sudo -u postgres dropdb --if-exists --force $DB
rm -rf $FS/$DB
step restore
sudo -u postgres createdb -O odoo $DB
sudo -u postgres pg_restore -d $DB --no-owner --role=odoo -j 4 $(ls -t /var/backups/odoo/eot_main_pre_m6_*.dump | head -1) 2>&1 | grep -v "^$" | tail -3
cp -a $FS/eot_main $FS/$DB
step worktree
cd /opt/odoo/themes/theme_eot_custom && git fetch -q --prune origin
rm -rf $WT; mkdir -p $WT
git worktree prune; git worktree add -f --detach $WT/theme_eot_custom $REF >/dev/null 2>&1 || cp -a . $WT/theme_eot_custom
( cd $WT/theme_eot_custom && git checkout -q --detach $REF && git log --oneline -1 )
chown -R odoo:odoo $WT
step scss
$PY -c "
import sass,glob
for f in glob.glob('$WT/theme_eot_custom/static/src/scss/pages.scss'):
    css=sass.compile(filename=f,output_style='compressed'); print('scss ok',f.split('/')[-1],len(css),'bytes')
" 2>&1 | tail -3
step upgrade
sudo -u odoo $PY $BIN -c /etc/odoo20.conf -d $DB --db-filter="^$DB\$" --addons-path=$AP -u theme_eot_custom --stop-after-init --no-http > /tmp/m6_upgrade.log 2>&1
echo "rc=$?"; grep -E " (ERROR|CRITICAL|WARNING) |Traceback|ParseError" /tmp/m6_upgrade.log | cut -c1-300 | head -15
step cleanup-dry
EOT_DRY_RUN=1 sudo -E -u odoo $PY $BIN shell -c /etc/odoo20.conf -d $DB --db-filter="^$DB\$" --addons-path=$AP --no-http < $WT/theme_eot_custom/scripts/m6_cleanup.py 2>&1 | grep -vE "^(20[0-9]{2}-| *$|>>>|\.\.\.)" | tail -12
step cleanup
sudo -u odoo $PY $BIN shell -c /etc/odoo20.conf -d $DB --db-filter="^$DB\$" --addons-path=$AP --no-http < $WT/theme_eot_custom/scripts/m6_cleanup.py 2>&1 | grep -vE "^(20[0-9]{2}-| *$|>>>|\.\.\.)" | tail -12
step serve
sudo -u odoo setsid nohup $PY $BIN -c /etc/odoo20.conf -d $DB --db-filter="^$DB\$" --addons-path=$AP --http-port=8070 --workers=0 --max-cron-threads=0 --no-database-list > /tmp/m6_serve.log 2>&1 &
for i in $(seq 1 60); do curl -s -o /dev/null -H "Host: www.eot.ir" http://127.0.0.1:8070/web/login && break; sleep 2; done
step ready
