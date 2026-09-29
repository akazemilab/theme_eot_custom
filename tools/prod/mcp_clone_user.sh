#!/usr/bin/env bash
# Deployed as /opt/eot-mcp/clone_user.sh, root-owned; same shape as
# rehearse.sh. Re-validates the db name itself (never trust the caller's
# check alone for an action that creates an account) before dropping to the
# odoo user and feeding it clone_user.py, exactly like `eot clone-user`.
#
#   clone_user.sh DB
set -uo pipefail
db=${1:?usage: clone_user.sh DB}
case "$db" in
  eot_main|eot_main_*) echo "!! refusing: accounts are never created on the live db ($db)"; exit 1 ;;
  eot_*) ;;
  *) echo "!! refusing: db name must start with eot_ (got '$db')"; exit 1 ;;
esac
sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell \
  -c /etc/odoo20.conf -d "$db" --no-http --log-level=error < /opt/eot-mcp/clone_user.py
