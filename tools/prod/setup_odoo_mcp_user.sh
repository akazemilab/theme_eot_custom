#!/usr/bin/env bash
# One-time setup, run as root on eot-odoo-prod:
#   - creates the dedicated Odoo user mcp@eot.ir (internal user + Website
#     Designer; NOT an administrator) on eot_main, if it doesn't exist
#   - generates an Odoo API key for it and writes it ONLY to
#     /opt/eot-mcp/odoo.env (root:eotmcp, mode 640). The key is never printed.
# Then restart the gateway so odoo_execute can log in:
#   systemctl restart eot-mcp
set -euo pipefail
ENVF=/opt/eot-mcp/odoo.env
LOGIN=mcp@eot.ir
if [ -s "$ENVF" ]; then echo "$ENVF already exists - delete it first to rotate the key"; exit 1; fi
umask 037
KEY=$(sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell \
  -c /etc/odoo20.conf -d eot_main --no-http --log-level=error 2>/tmp/mcp_user_setup.err <<PY | grep '^KEY=' | cut -d= -f2
import datetime
U = env['res.users'].with_context(no_reset_password=True)
u = U.search([('login', '=', '$LOGIN')], limit=1)
if not u:
    u = U.create({
        'name': 'MCP (Claude)', 'login': '$LOGIN', 'email': '$LOGIN',
        'group_ids': [(6, 0, [env.ref('base.group_user').id, env.ref('website.group_website_designer').id])],
    })
key = env['res.users.apikeys'].with_user(u)._generate(None, 'eot-mcp', datetime.datetime.now() + datetime.timedelta(days=85))
env.cr.commit()
print('KEY=' + key)
PY
)
[ -n "$KEY" ] || { echo "failed to generate key; last error:"; tail -5 /tmp/mcp_user_setup.err; exit 1; }
printf 'ODOO_LOGIN=%s\nODOO_API_KEY=%s\n' "$LOGIN" "$KEY" > "$ENVF"
chown root:eotmcp "$ENVF"; chmod 640 "$ENVF"
echo "OK: $ENVF written (key not shown). Now: systemctl restart eot-mcp"
