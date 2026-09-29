#!/usr/bin/env python3
"""EOT MCP gateway - real, narrowly-scoped tools for the theme_eot_custom project.

Runs as the unprivileged `eotmcp` system user (no login shell) on
eot-odoo-prod, behind nginx at https://eot.innerquest.me/mcp (Cloudflare in
front). This is what lets Claude check status, deploy, and now verify the
live site WITHOUT the session being linked to any particular device -
unlike the VPS `eot` toolkit (tools/vps/eot), which is only reachable by
proxying through a device's local MCP config.

Capabilities are deliberately limited to exactly what this project needs,
via specific sudoers entries and group membership - NOT a blanket root
shell:

  - deploy_theme  : sudo access to exactly one script,
                    /opt/odoo/themes/theme_eot_custom/scripts/deploy.sh
  - odoo_status   : sudo access to exactly `systemctl status/is-active odoo20`
  - read_odoo_log : membership in `systemd-journal` group (read-only, no sudo)
  - git_log       : sudo access to exactly one fixed command
                    (`git -C .../theme_eot_custom log -50 --oneline --decorate`);
                    eotmcp itself cannot traverse /opt/odoo (root:odoo 750),
                    so this goes through sudo like deploy_theme/odoo_status
                    rather than widening eotmcp's own filesystem access
  - scss_check    : sudo access to exactly one fixed script,
                    /opt/eot-mcp/scss_check.sh (root-owned, no arguments) -
                    same shape as deploy_theme, for the same reason as git_log
  - check_site, check_links, placeholders : NO sudo, NO filesystem access at
                    all - pure HTTP GET against 127.0.0.1:8069 (stdlib
                    urllib only, so no extra dependency). This is the read
                    side of `eot check` / `eot links` / `eot placeholders`
                    (tools/vps/eotcheck.py), reimplemented against stdlib so
                    it can run under eotmcp's own account with zero grants.
                    Never signs in and never touches a rehearsal clone -
                    that stays on the `eot` toolkit, reachable only via a
                    linked device, since it's a bigger privilege surface
                    (account creation, DB clones) than this gateway should
                    carry on a bearer-token HTTP endpoint.

Auth: static bearer token from MCP_TOKEN_FILE. Never logs Authorization
header, querystring, or tool arguments (deploy refs, grep patterns) - only
method names and outcomes.
"""
import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urljoin, urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("eot-mcp")

TOKEN = open(os.environ["MCP_TOKEN_FILE"]).read().strip()
PROTOCOL_VERSION = "2025-06-18"
DEPLOY_SCRIPT = "/opt/odoo/themes/theme_eot_custom/scripts/deploy.sh"
SCSS_SCRIPT = "/opt/eot-mcp/scss_check.sh"
REPO_DIR = "/opt/odoo/themes/theme_eot_custom"
LOCAL_ODOO = "http://127.0.0.1:8069"  # never the rehearsal clone (:8070) - live only
SITE_HOST = "www.eot.ir"

TOOLS = [
    {
        "name": "deploy_theme",
        "description": (
            "Deploy a branch or commit of theme_eot_custom to the eot_main "
            "database. Fetches, checks out the ref, upgrades the module, "
            "restarts odoo20, and verifies website 1 shows the change and "
            "website 3 is untouched. Can take a couple of minutes."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"ref": {"type": "string", "description": "Branch or commit, e.g. main or milestone/02-header-footer"}},
            "required": ["ref"],
        },
    },
    {
        "name": "read_odoo_log",
        "description": "Read recent odoo20 journal entries. Read-only.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "journalctl --since value, e.g. '-15min', '2026-09-28 06:00:00'. Default '-15min'."},
                "grep": {"type": "string", "description": "Optional case-insensitive substring filter, e.g. 'ERROR' or 'theme_eot_custom'."},
            },
        },
    },
    {
        "name": "odoo_status",
        "description": "Check whether the odoo20 service is active, and how long it's been running.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "git_log",
        "description": "Show recent commits in the theme_eot_custom repo on the server (what's actually deployed there right now, not what's on GitHub).",
        "inputSchema": {
            "type": "object",
            "properties": {"n": {"type": "integer", "description": "Number of commits, default 10, max 50."}},
        },
    },
    {
        "name": "scss_check",
        "description": "Compile the theme's SCSS files with libsass on the server and report per-file rule counts and any @import url(...) (which breaks the asset bundle - CLAUDE.md pitfall #1). Read-only.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "check_site",
        "description": (
            "Render one or more LIVE page paths (never the rehearsal clone) and report: HTTP status, "
            "<title>, whether it's the deployed theme (eot-theme marker), traceback detection, and - for "
            "the homepage or any path whose stylesheet bundle is fetched - whether that CSS bundle actually "
            "parses (catches '200 OK but 0 rules', CLAUDE.md pitfall #1/#2)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"paths": {"type": "array", "items": {"type": "string"}, "description": "Site-relative paths starting with '/', e.g. ['/', '/about']. Default ['/']. Max 10."}},
        },
    },
    {
        "name": "check_links",
        "description": "Fetch a LIVE page and report every same-site internal link that does NOT return 200 (dead links, unpublished pages).",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Site-relative path starting with '/'. Default '/'."}},
        },
    },
    {
        "name": "placeholders",
        "description": "Crawl the live sitemap and scan every rendered page for demo placeholders (lorem ipsum, yourcompany.example, 555-555-xxxx, etc.) and pages that don't return 200. Can take a minute for the whole site.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max sitemap pages to scan, default 60, max 300."}},
        },
    },
]

PLACEHOLDER_RE = re.compile(
    r"555-555-\d{3,4}|\+1 ?\(?650\)?[\d \-]{6,}|info@yourcompany|yourcompany@"
    r"|yourcompany\.example|@example\.com|lorem ipsum|\bMy Company\b"
    r"|\bYour Company\b|\bYourCompany\b|Company Name|\[YOUR[^\]]*\]",
    re.I,
)


def run(cmd, timeout):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"timed out after {timeout}s"


def http_get(path, timeout=20):
    """GET a path from the LIVE site on this box (never the :8070 clone).
    Paths often carry raw Persian text (stored href attributes aren't always
    percent-encoded - CLAUDE.md pitfall #13); urllib needs an ASCII URL."""
    safe_path = quote(path, safe="/%?=&:@,;+")
    req = urllib.request.Request(
        LOCAL_ODOO + safe_path,
        headers={"Host": SITE_HOST, "Cookie": "frontend_lang=fa_IR", "User-Agent": "eot-mcp-check/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.css, self.title, self.marker, self._in_title = [], None, False, False

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "link" and "stylesheet" in (a.get("rel") or ""):
            self.css.append(a.get("href"))
        elif tag == "meta" and a.get("name") == "eot-theme":
            self.marker = True
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, d):
        if self._in_title:
            self.title = (self.title or "") + d


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, a):
        if tag == "a":
            h = dict(a).get("href")
            if h and not h.startswith(("#", "mailto:", "tel:", "javascript:")):
                self.hrefs.append(h)


def _valid_path(p):
    return isinstance(p, str) and p.startswith("/") and not any(c.isspace() for c in p) and ".." not in p


def check_site(paths):
    out = []
    for path in paths[:10]:
        if not _valid_path(path):
            out.append(f"{path!r}: invalid path (must start with '/', no whitespace or '..')")
            continue
        status, text, _ = http_get(path)
        p = Assets()
        p.feed(text)
        trace = "Traceback" in text or "Internal Server Error" in text
        line = f"{status} {path}{'  TRACEBACK' if trace else ''} | {(p.title or '-').strip()} | marker={'yes' if p.marker else 'NO'}"
        out.append(line)
        for href in dict.fromkeys(p.css):
            full = urljoin(LOCAL_ODOO + path, href)
            cpath = full[len(LOCAL_ODOO):] if full.startswith(LOCAL_ODOO) else None
            if not cpath:
                continue
            cstatus, ctext, _ = http_get(cpath)
            rules = ctext.count("{")
            verdict = f"~{rules} rules"
            if rules < 5 and len(ctext) > 10000:
                verdict += f" !! BROKEN (big file, ~no rules); starts: {ctext[:100]!r}"
            out.append(f"  css {cstatus} {len(ctext) // 1024}KB {cpath[-70:]} | {verdict}")
    return True, "\n".join(out)


def check_links(path):
    if not _valid_path(path):
        return False, f"invalid path: {path!r}"
    status, text, _ = http_get(path)
    p = Links()
    p.feed(text)
    targets = [urljoin(LOCAL_ODOO + path, h).split("#")[0] for h in p.hrefs]
    targets = [t for t in dict.fromkeys(targets) if t.startswith(LOCAL_ODOO)]
    bad = []
    for t in targets:
        tpath = t[len(LOCAL_ODOO):]
        try:
            tstatus, _, _ = http_get(tpath, timeout=15)
        except Exception as e:  # noqa: BLE001
            tstatus = f"ERR {e}"
        if tstatus != 200:
            bad.append(f"  {tstatus} {unquote(urlparse(t).path)}")
    summary = f"{len(targets)} internal links on {path}: " + ("ALL OK" if not bad else f"{len(bad)} BROKEN")
    return True, summary + ("\n" + "\n".join(bad) if bad else "")


def placeholders(limit=60):
    limit = min(int(limit or 60), 300)
    status, sm, _ = http_get("/sitemap.xml")
    locs = re.findall(r"<loc>([^<]+)</loc>", sm)
    urls = []
    for loc in locs:
        path = urlparse(loc).path + (("?" + urlparse(loc).query) if urlparse(loc).query else "")
        if path.endswith(".xml"):
            _, sub, _ = http_get(path)
            urls += [urlparse(u).path for u in re.findall(r"<loc>([^<]+)</loc>", sub)]
        else:
            urls.append(path)
    urls = list(dict.fromkeys(urls))[:limit]
    out = [f"scanning {len(urls)} pages"]
    hits, broken = {}, []
    for u in urls:
        try:
            ustatus, html, _ = http_get(u, timeout=15)
        except Exception as e:  # noqa: BLE001
            out.append(f"  ERR {u} {e}")
            continue
        if ustatus != 200:
            broken.append(f"{ustatus} {unquote(u)}")
            continue
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        for m in set(x.group(0) for x in PLACEHOLDER_RE.finditer(body)):
            hits.setdefault(m, []).append(u)
    if not hits:
        out.append("NO PLACEHOLDERS FOUND")
    for m, pages in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        out.append(f"  {m!r} on {len(pages)} page(s): {', '.join(pages[:5])}{' ...' if len(pages) > 5 else ''}")
    if broken:
        out.append(f"BROKEN PAGES in sitemap ({len(broken)}):")
        out += ["  " + b for b in broken]
    return True, "\n".join(out)


def call_tool(name, args):
    if name == "deploy_theme":
        ref = args.get("ref", "")
        if not ref or any(c.isspace() for c in ref) or ".." in ref:
            return False, f"invalid ref: {ref!r}"
        rc, out, err = run(["sudo", "-n", DEPLOY_SCRIPT, ref], timeout=280)
        ok = rc == 0
        return ok, (out + ("\n" + err if err else "")).strip()[-6000:]

    if name == "odoo_status":
        rc, out, err = run(["sudo", "-n", "/usr/bin/systemctl", "status", "odoo20", "--no-pager"], timeout=15)
        return rc == 0, (out + err).strip()[-3000:]

    if name == "read_odoo_log":
        since = args.get("since", "-15min")
        cmd = ["journalctl", "-u", "odoo20", "--since", since, "--no-pager"]
        rc, out, err = run(cmd, timeout=20)
        if rc != 0:
            return False, err.strip()[-2000:]
        grep = args.get("grep")
        if grep:
            gl = grep.lower()
            out = "\n".join(l for l in out.splitlines() if gl in l.lower())
        lines = out.splitlines()
        if len(lines) > 300:
            lines = lines[-300:]
        return True, "\n".join(lines)[-8000:] or "(no matching lines)"

    if name == "git_log":
        # Fixed sudo command (exact-match sudoers entry, capped at 50) - eotmcp
        # can't read /opt/odoo itself, so this is gated the same way as the
        # other two privileged tools rather than widening filesystem access.
        n = min(int(args.get("n", 10) or 10), 50)
        rc, out, err = run(
            ["sudo", "-n", "/usr/bin/git", "-C", REPO_DIR, "log", "-50", "--oneline", "--decorate"],
            timeout=15,
        )
        if rc != 0:
            return False, (out + err).strip()[-2000:]
        return True, "\n".join(out.splitlines()[:n])

    if name == "scss_check":
        # Same shape as deploy_theme/git_log: one fixed, root-owned, no-argument
        # script - not a way to run arbitrary root commands.
        rc, out, err = run(["sudo", "-n", SCSS_SCRIPT], timeout=30)
        return rc == 0, (out + ("\n" + err if err else "")).strip()[-4000:]

    if name == "check_site":
        return check_site(args.get("paths") or ["/"])

    if name == "check_links":
        return check_links(args.get("path") or "/")

    if name == "placeholders":
        return placeholders(args.get("limit", 60))

    return False, f"unknown tool {name!r}"


class Handler(BaseHTTPRequestHandler):
    server_version = "eot-mcp/1.0"

    def log_message(self, fmt, *args):
        pass  # custom logging only; never log headers/querystring/tool args

    def _authed(self):
        return self.headers.get("Authorization", "") == f"Bearer {TOKEN}"

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send(405, {"error": "use POST"})

    def do_POST(self):
        if self.path.split("?")[0] != "/mcp":
            self._send(404, {"error": "not found"}); return
        if not self._authed():
            self._send(403, {"error": "forbidden"}); return

        length = int(self.headers.get("Content-Length", 0))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"jsonrpc": "2.0", "id": None,
                              "error": {"code": -32700, "message": "parse error"}})
            return

        method, rid = req.get("method"), req.get("id")
        log.info("method=%s", method)

        if method == "initialize":
            self._send(200, {"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": req.get("params", {}).get("protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "eot-mcp", "version": "1.0.0"},
            }})
        elif method == "notifications/initialized":
            self.send_response(202); self.send_header("Content-Length", "0"); self.end_headers()
        elif method == "ping":
            self._send(200, {"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "tools/list":
            self._send(200, {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            name = req.get("params", {}).get("name")
            args = req.get("params", {}).get("arguments", {}) or {}
            if name not in {t["name"] for t in TOOLS}:
                self._send(200, {"jsonrpc": "2.0", "id": rid,
                                  "error": {"code": -32602, "message": f"unknown tool {name!r}"}})
                return
            try:
                ok, text = call_tool(name, args)
            except Exception as e:
                log.exception("tool %s failed", name)
                ok, text = False, f"internal error: {e}"
            self._send(200, {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": text}],
                "isError": not ok,
            }})
        else:
            self._send(200, {"jsonrpc": "2.0", "id": rid,
                              "error": {"code": -32601, "message": f"unknown method {method!r}"}})


if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "8091"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
