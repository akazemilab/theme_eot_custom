#!/usr/bin/env bash
# Deployed as /opt/eot-mcp/scss_check.sh, root-owned, no arguments - run only
# via the exact sudoers entry for the eotmcp system user (see eot-mcp.sudoers
# and mcp_server.py's scss_check tool). Compiles the theme's SCSS with the
# same libsass the asset bundler uses, so a broken file is caught before an
# upgrade rather than after ("200 OK, 0 rules" - CLAUDE.md pitfall #1).
set -uo pipefail
cd /opt/odoo/themes/theme_eot_custom || exit 1
/opt/odoo/venv/bin/python3 - <<'PY'
import glob, sass
bad = 0
for f in sorted(glob.glob('static/src/scss/*.scss')):
    try:
        css = sass.compile(filename=f, output_style='compressed')
        flag = '  !! @import url' if '@import url' in open(f).read() else ''
        print('ok  %-40s %6d bytes%s' % (f, len(css), flag))
    except sass.CompileError as e:
        bad += 1
        print('ERR', f, str(e).splitlines()[0][:200])
raise SystemExit(bad)
PY
