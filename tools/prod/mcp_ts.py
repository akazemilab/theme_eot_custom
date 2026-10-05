"""mcp_ts - tools-VPS tools for the eot.innerquest.me gateway (no Mac / device in the path).

Lives in the theme repo next to mcp_server.py (deployed by `eot mcp-update`); source of truth for the VPS side is
talentsearch_odoo/tools/gw/ts_gw.py. The gateway (user eotmcp on eot-odoo-prod) reaches the tools VPS over ssh with
its own key, /opt/eot-mcp/ts_gw_key. On the VPS that key is pinned in root's authorized_keys to
`command="/usr/local/bin/ts-gw",restrict,from="95.38.235.225"`, so the key can do nothing but the allow-listed ops of
ts-gw (the VPS re-validates everything; the checks here only shape the request). Request = one JSON object on stdin.
Never logs arguments.
"""
import json
import subprocess

VPS = 'root@95.38.234.86'
KEY = '/opt/eot-mcp/ts_gw_key'
KNOWN = '/opt/eot-mcp/ts_gw_known_hosts'

_S = {'type': 'string'}
_L = {'type': 'array', 'items': {'type': 'string'}}
_C = {'type': 'boolean', 'description': 'Required true for live-changing or destructive commands (ship, deploy, clean --yes, forced git flags).'}
REPOS = '/root/talentsearch_odoo (default) | /root/ts_wt_s1 | /root/ts_wt_s2 | /root/eot-tools/repo'

TOOLS = [
    {'name': 'ts', 'description': (
        'Run the Talent Search `ts` toolkit on the tools VPS (no device needed). args = the words after `ts`, e.g. '
        '["slots"], ["check"], ["rehearse","eot_ts90","","ts_panel"], ["wait","reh_eot_ts90"], ["keep","eot_ts91","ts_panel"] '
        '(slot 1), ["test","eot_ts91","ts_http_pv3.py"], ["db","errors","eot_ts91"], ["dump","check"], ["shots","eot_ts91"], '
        '["push","msg"], ["ship","INS","UPG","LABEL"] (confirm=true), ["live"]. Not exposed: bg, domain, guard. '
        'Each call must end within ~55 s: long work runs as a job and is followed with ["wait",NAME] (blocks <= 40 s). '
        'Returns the command output (verdict lines).'),
     'inputSchema': {'type': 'object', 'properties': {'args': _L, 'slot': {'type': 'integer', 'description': '0 (default), 1 or 2'}, 'confirm': _C},
                     'required': ['args']}},
    {'name': 'eot_vps', 'description': (
        'Run the eot.ir `eot` toolkit on the tools VPS: status, check, links, placeholders, verify, text, find, view, sql, log, '
        'render, routes, audit, job, jobs, wait, rehearse, rehearse-log, rehearse-stop, clone-user, backup, deploy/ship (confirm=true).'),
     'inputSchema': {'type': 'object', 'properties': {'args': _L, 'confirm': _C}, 'required': ['args']}},
    {'name': 'vps_read', 'description': (
        'Read a numbered slice (max 400 lines) of a text file, or list a directory, on the tools VPS under the repos '
        '(' + REPOS + '), /root/ts-jobs, /root/eot-jobs, /root/share. Read only the lines you need.'),
     'inputSchema': {'type': 'object', 'properties': {'path': _S, 'start': {'type': 'integer'}, 'end': {'type': 'integer'}},
                     'required': ['path']}},
    {'name': 'vps_write', 'description': 'Create or replace a text file on the tools VPS under a repo (' + REPOS + ') or /root/share/in. Prefer vps_patch for edits of existing files.',
     'inputSchema': {'type': 'object', 'properties': {'path': _S, 'content': _S}, 'required': ['path', 'content']}},
    {'name': 'vps_patch', 'description': 'Apply a unified diff (git apply, checked first) in a repo on the tools VPS; returns git status. root: ' + REPOS,
     'inputSchema': {'type': 'object', 'properties': {'root': _S, 'diff': _S}, 'required': ['diff']}},
    {'name': 'vps_git', 'description': (
        'git in a repo on the tools VPS (root: ' + REPOS + '). Subcommands: status diff log show add commit restore rev-parse '
        'branch fetch pull push(origin BRANCH only, no force) switch checkout stash reset ls-files blame grep. --hard/--force need confirm=true.'),
     'inputSchema': {'type': 'object', 'properties': {'root': _S, 'args': _L, 'confirm': _C}, 'required': ['args']}},
    {'name': 'vps_image', 'description': 'Return a png/jpg/webp (<= 3 MB) from /root/share/out, /root/ts-jobs or /root/eot-jobs on the tools VPS as an image (e.g. ts shots output). Costs context: look at few.',
     'inputSchema': {'type': 'object', 'properties': {'path': _S}, 'required': ['path']}},
    {'name': 'vps_inspect', 'description': (
        'Read-only diagnostics on the tools VPS, no shell: argv[0] in ls grep head tail wc df du free uptime ps ss find stat md5sum '
        'date systemctl(status|is-active|list-units|show|cat) journalctl cat file nginx(-t) dig getent curl(GET). File paths must be '
        'under the repos, /root/ts-jobs, /root/eot-jobs, /root/share, /etc/nginx, /etc/systemd/system, /var/log, /usr/local/bin, /tmp.'),
     'inputSchema': {'type': 'object', 'properties': {'argv': _L}, 'required': ['argv']}},
]
NAMES = {t['name'] for t in TOOLS}
OP = {'ts': 'ts', 'eot_vps': 'eot', 'vps_read': 'read', 'vps_write': 'write', 'vps_patch': 'patch', 'vps_git': 'git',
      'vps_image': 'image', 'vps_inspect': 'inspect'}


def call(name, args):
    """Returns (ok, content_list) in MCP tool-result shape."""
    req = dict(args or {}, op=OP[name])
    try:
        p = subprocess.run(['ssh', '-i', KEY, '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=yes',
                            '-o', 'UserKnownHostsFile=' + KNOWN, '-o', 'ConnectTimeout=10', VPS, 'ts-gw'],
                           input=json.dumps(req), capture_output=True, text=True, timeout=58)
    except subprocess.TimeoutExpired:
        return False, [{'type': 'text', 'text': '!! tools VPS did not answer within 58 s (start long work as a job and wait)'}]
    try:
        r = json.loads(p.stdout)
    except ValueError:
        return False, [{'type': 'text', 'text': '!! tools VPS unreachable or bad reply (ssh rc=%s): %s' % (p.returncode, p.stderr.strip()[-300:])}]
    content = []
    if r.get('image'):
        content.append({'type': 'image', 'data': r['image'], 'mimeType': r.get('mime', 'image/png')})
    content.append({'type': 'text', 'text': r.get('text') or ''})
    return bool(r.get('ok')), content
