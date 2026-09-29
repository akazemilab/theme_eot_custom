#!/usr/bin/env bash
# Deployed as /opt/eot-mcp/rehearse_stop.sh, root-owned; same shape as
# rehearse.sh (see its header comment). Mirrors tools/vps/eot's
# "rehearse-stop" case exactly, including the bracket-pattern pkill fix
# (CLAUDE.md: pkill -f over ssh/sudo can match its own command line).
#
#   rehearse_stop.sh DB
set -uo pipefail
db=${1:?usage: rehearse_stop.sh DB}
case "$db" in
  eot_main|eot_main_*) echo "!! refusing: '$db' looks like the live db"; exit 1 ;;
  eot_*) ;;
  *) echo "!! refusing: db name must start with eot_ (got '$db')"; exit 1 ;;
esac
pkill -f "[-]d $db" 2>/dev/null
sleep 1
sudo -u postgres dropdb --if-exists --force "$db"
rm -rf "/opt/odoo/.local/share/Odoo/filestore/$db"
echo "pg:$(sudo -u postgres psql -Atc "select 1 from pg_database where datname='$db'")"
echo "fs:$(test -d "/opt/odoo/.local/share/Odoo/filestore/$db" && echo present || echo gone)"
echo "proc:$(pgrep -af "[-]d $db" | wc -l)"
