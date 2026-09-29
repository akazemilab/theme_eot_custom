#!/usr/bin/env bash
# Deployed as /opt/eot-mcp/rehearse.sh, root-owned, called only via the exact
# sudoers entry for eotmcp (`eotmcp ALL=(root) NOPASSWD: /opt/eot-mcp/rehearse.sh *`).
# Validates its own arguments before doing anything irreversible - the
# sudoers wildcard fixes WHICH script can run as root, this script fixes
# WHAT it's allowed to do with that (CLAUDE.md "assert preconditions" pattern).
#
#   rehearse.sh REF DB
set -uo pipefail
ref=${1:?usage: rehearse.sh REF DB}
db=${2:?usage: rehearse.sh REF DB}
case "$db" in
  eot_main|eot_main_*) echo "!! refusing: '$db' looks like the live db"; exit 1 ;;
  eot_*) ;;
  *) echo "!! refusing: db name must start with eot_ (got '$db')"; exit 1 ;;
esac
if [[ "$ref" =~ [[:space:]] ]] || [[ "$ref" == *..* ]]; then
  echo "!! invalid ref: $ref"; exit 1
fi
exec bash /opt/odoo/themes/theme_eot_custom/scripts/rehearse.sh "$ref" "$db"
