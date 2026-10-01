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
  - sql_query     : sudo access (as the postgres user, not root) to exactly
                    one fixed psql invocation with fixed flags - the query
                    text goes over stdin, so the sudoers grant never widens
                    with the query. The tool itself refuses anything that
                    isn't a single read-only SELECT/WITH statement before it
                    ever reaches sudo.
  - rehearse, rehearse_stop, clone_user : sudo access to three fixed,
                    root-owned wrapper scripts under /opt/eot-mcp/ (same
                    shape as deploy_theme). Each wrapper re-validates its own
                    db argument (must start with `eot_`, never `eot_main`)
                    before doing anything - the tool-level check and the
                    wrapper's own check are independent, so a bug in one
                    doesn't expose the live db.
  - audit         : no sudo. Headless Chromium (installed via snap - see
                    tools/vps/install.sh's note on why: Playwright's own CDN
                    is geo-blocked here, same as the VPS) running as eotmcp,
                    fetching static/tools/eot_audit.js over HTTP from the
                    site itself rather than reading the repo, so it needs no
                    filesystem grant either.

This host has far more headroom than the VPS (12 GB RAM vs. 1 GB), so audit
and rehearse run directly here rather than needing a second machine - no
device, no tunnel.

Auth: static bearer token from MCP_TOKEN_FILE. Never logs Authorization
header, querystring, or tool arguments (deploy refs, grep patterns) - only
method names and outcomes.
"""
import json
import logging
import os
import re
import subprocess
import sys
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
REHEARSE_SCRIPT = "/opt/eot-mcp/rehearse.sh"
REHEARSE_STOP_SCRIPT = "/opt/eot-mcp/rehearse_stop.sh"
CLONE_USER_SCRIPT = "/opt/eot-mcp/clone_user.sh"
BROWSER_PY = "/opt/eot-mcp/browser/venv/bin/python3"
CHROME = "/snap/chromium/current/usr/lib/chromium-browser/chrome"
REPO_DIR = "/opt/odoo/themes/theme_eot_custom"
LOCAL_ODOO = "http://127.0.0.1:8069"  # live
CLONE_ODOO = "http://127.0.0.1:8070"  # a rehearsal, if one is currently being served
SITE_HOST = "www.eot.ir"


def _valid_db(db):
    return isinstance(db, str) and db.startswith("eot_") and not db.startswith("eot_main") and db.replace("_", "").isalnum()

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
    {
        "name": "sql_query",
        "description": "Run a READ-ONLY query (SELECT or WITH only - anything else is refused) against the eot_main database and return compact pipe-separated rows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A single SELECT or WITH statement. No semicolons except one optional trailing one."},
                "limit": {"type": "integer", "description": "Max rows to return, default 200, max 1000."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "odoo_execute",
        "description": (
            "Call any Odoo ORM method on the eot_main database as the dedicated "
            "MCP user (read, create, write). Use for small content edits "
            "(ir.ui.view arch, website.page, ir.model.data, translations) instead of a "
            "theme redeploy. ALWAYS read the target records first and tell the user "
            "what will change. unlink needs confirm=true. Writes to security/automation "
            "models are refused. Note: a later theme deploy re-applies theme views from "
            "git and overwrites DB edits to them - keep structure in the theme."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "e.g. ir.ui.view, website.page, res.partner"},
                "method": {"type": "string", "description": "e.g. search_read, read, write, create, fields_get, search_count"},
                "args": {"type": "array", "description": "Positional args (domain, ids, values...)"},
                "kwargs": {"type": "object", "description": "Named args (fields, limit, order, context)"},
                "confirm": {"type": "boolean", "description": "Required true for unlink."},
            },
            "required": ["model", "method"],
        },
    },
    {
        "name": "rehearse",
        "description": (
            "Rehearse a branch/commit on a disposable clone of eot_main: restore the latest backup into DB, "
            "upgrade theme_eot_custom from that ref, and serve it on :8070. NEVER touches the live database. "
            "Takes 15-40s; call rehearse_stop when done. DB must start with 'eot_' and never be eot_main."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "ref": {"type": "string", "description": "Branch or commit, e.g. origin/fix/my-branch"},
                "db": {"type": "string", "description": "Disposable database name, e.g. eot_rehearse_1. Must start with 'eot_'."},
            },
            "required": ["ref", "db"],
        },
    },
    {
        "name": "rehearse_stop",
        "description": "Stop and drop a rehearsal clone started by `rehearse` (process, database, filestore), with proof it's actually gone. Refuses eot_main*.",
        "inputSchema": {
            "type": "object",
            "properties": {"db": {"type": "string", "description": "The rehearsal database name to tear down."}},
            "required": ["db"],
        },
    },
    {
        "name": "clone_user",
        "description": "Create (or reset) a portal test user on a rehearsal clone (NEVER on eot_main) so signed-in pages (/my/*) can be checked. Returns a login and a one-time password.",
        "inputSchema": {
            "type": "object",
            "properties": {"db": {"type": "string", "description": "The rehearsal database (from `rehearse`), not eot_main."}},
            "required": ["db"],
        },
    },
    {
        "name": "audit",
        "description": (
            "Headless-Chromium design/quality audit (overflow, WCAG contrast, leftover English UI text, broken "
            "images, heading font, tab title) of one or more paths, on LIVE by default. Set clone:true to audit "
            "a rehearsal instead (after calling `rehearse`); add login/password (from `clone_user`) to also check "
            "signed-in pages. Reports only pages with problems."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "paths": {"type": "array", "items": {"type": "string"}, "description": "Site-relative paths. Default ['/']. Max 15."},
                "widths": {"type": "array", "items": {"type": "integer"}, "description": "Viewport widths to check. Default [1280, 375]."},
                "clone": {"type": "boolean", "description": "Audit the rehearsal clone on :8070 instead of live. Default false."},
                "login": {"type": "string", "description": "Optional: sign in first (clone only), from clone_user."},
                "password": {"type": "string", "description": "Optional: password for login (clone only), from clone_user."},
            },
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


SQL_OK_RE = re.compile(r"^\s*(select|with)\b", re.I)


def sql_query(query, limit=200):
    if not isinstance(query, str) or not query.strip():
        return False, "empty query"
    q = query.strip().rstrip(";").strip()
    if ";" in q:
        return False, "only a single statement is allowed (no ';' except one optional trailing one)"
    if not SQL_OK_RE.match(q):
        return False, "read-only: query must start with SELECT or WITH"
    limit = min(int(limit or 200), 1000)
    # psql reads the query from stdin - it's never part of the argv the
    # sudoers rule has to match. A single-char, space-free delimiter keeps
    # the sudoers Cmnd_Spec a plain exact match (no quoting to get wrong).
    p = subprocess.run(
        ["sudo", "-n", "-u", "postgres", "/usr/bin/psql", "-d", "eot_main", "-At", "-F", "|", "-v", "ON_ERROR_STOP=1"],
        input=q, capture_output=True, text=True, timeout=25,
    )
    if p.returncode != 0:
        return False, (p.stdout + p.stderr).strip()[-2000:]
    lines = p.stdout.splitlines()
    truncated = len(lines) > limit
    return True, "\n".join(lines[:limit]) + (f"\n... ({len(lines) - limit} more rows)" if truncated else "")


ODOO_ENV_FILE = os.environ.get("ODOO_ENV_FILE", "/opt/eot-mcp/odoo.env")
ODOO_DB = "eot_main"
# Models whose writes could change who can do what, run code, or leak secrets.
ODOO_WRITE_DENY = {
    "res.users", "res.groups", "res.users.apikeys", "ir.rule", "ir.model.access",
    "ir.config_parameter", "ir.cron", "ir.actions.server", "base.automation",
    "ir.model", "ir.model.fields", "ir.module.module", "ir.mail_server",
    "res.users.log", "ir.attachment",
}
ODOO_READ_METHODS = {"search", "read", "search_read", "search_count", "fields_get", "name_search",
                     "read_group", "name_get", "default_get", "check_access_rights"}
ODOO_WRITE_METHODS = {"write", "create", "unlink", "copy"}
_odoo_session = {}


def _odoo_login():
    import xmlrpc.client
    if "uid" in _odoo_session:
        return _odoo_session
    cfg = {}
    for line in open(ODOO_ENV_FILE, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip("'\"")
    common = xmlrpc.client.ServerProxy(LOCAL_ODOO + "/xmlrpc/2/common", allow_none=True)
    uid = common.authenticate(ODOO_DB, cfg["ODOO_LOGIN"], cfg["ODOO_API_KEY"], {})
    if not uid:
        raise RuntimeError("Odoo authentication failed for the MCP user")
    _odoo_session.update(uid=uid, key=cfg["ODOO_API_KEY"],
                         models=xmlrpc.client.ServerProxy(LOCAL_ODOO + "/xmlrpc/2/object", allow_none=True))
    return _odoo_session


def odoo_execute(model, method, args=None, kwargs=None, confirm=False):
    import xmlrpc.client
    if not (isinstance(model, str) and re.fullmatch(r"[a-z0-9_.]+", model)):
        return False, "invalid model"
    if not (isinstance(method, str) and re.fullmatch(r"[a-z][a-z0-9_]*", method)) or method.startswith("_"):
        return False, "invalid method (private/underscore methods are refused)"
    if method not in ODOO_READ_METHODS | ODOO_WRITE_METHODS:
        return False, "method not allowed; allowed: " + ", ".join(sorted(ODOO_READ_METHODS | ODOO_WRITE_METHODS))
    if method in ODOO_WRITE_METHODS and model in ODOO_WRITE_DENY:
        return False, f"writes to {model} are refused through this tool"
    if method == "unlink" and confirm is not True:
        return False, "unlink requires confirm=true after the user explicitly approved it"
    args, kwargs = list(args or []), dict(kwargs or {})
    if method in ("search_read", "search", "read_group") and "limit" not in kwargs:
        kwargs["limit"] = 50
    try:
        sess = _odoo_login()
        res = sess["models"].execute_kw(ODOO_DB, sess["uid"], sess["key"], model, method, args, kwargs)
    except xmlrpc.client.Fault as e:
        return False, "Odoo error: " + str(e.faultString)[-1500:]
    out = json.dumps({"ok": True, "result": res}, ensure_ascii=False, default=str)
    if len(out) > 30000:
        out = out[:30000] + " ...[truncated; narrow fields/limit]"
    log.info("odoo_execute %s.%s", model, method)  # never log args/values
    return True, out


def audit_pages(paths, widths, base, login=None, password=None):
    status, js, _ = http_get("/theme_eot_custom/static/tools/eot_audit.js", timeout=15)
    if status != 200:
        return False, f"could not fetch eot_audit.js from the running site (status {status})"
    from playwright.sync_api import sync_playwright  # imported lazily: only needed for this tool

    out, checked, bad = [], 0, 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = browser.new_context(locale="fa-IR")
        ctx.add_cookies([{"name": "frontend_lang", "value": "fa_IR", "url": base}])
        if login:
            pg = ctx.new_page()
            pg.goto(base + "/web/login", wait_until="load", timeout=30000)
            pg.fill("input[name=login]", login)
            pg.fill("input[name=password]", password or "")
            pg.click("form.oe_login_form button[type=submit]")
            pg.wait_for_load_state("load")
            out.append("signed in: " + ("yes" if "/my" in pg.url or "/odoo" in pg.url else f"NO ({pg.url})"))
            pg.close()
        for path in paths[:15]:
            if not _valid_path(path):
                out.append(f"{path!r}: invalid path"); continue
            for w in widths[:4]:
                page = ctx.new_page()
                page.set_viewport_size({"width": w, "height": 900})
                try:
                    resp = page.goto(base + path, wait_until="load", timeout=30000)
                    page.wait_for_timeout(300)
                    page.add_script_tag(content=js)
                    res = page.evaluate("eotAudit.page(window)")
                    res["status"] = resp.status if resp else 0
                except Exception as e:  # noqa: BLE001
                    res = {"ok": False, "problems": {"error": str(e).splitlines()[0][:160]}}
                finally:
                    page.close()
                checked += 1
                expected = 404 if path == "/this-page-does-not-exist" else 200
                if res.get("status", expected) != expected:
                    res["ok"] = False
                    res.setdefault("problems", {})["status"] = res.get("status")
                if not res.get("ok"):
                    bad += 1
                    out.append(f"{w:4d} {path}  {json.dumps(res.get('problems') or {}, ensure_ascii=False)}")
        browser.close()
    out.append(f"-- {checked} page-widths checked, {bad} with problems")
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

    if name == "sql_query":
        return sql_query(args.get("query", ""), args.get("limit", 200))

    if name == "odoo_execute":
        return odoo_execute(args.get("model", ""), args.get("method", ""), args.get("args"), args.get("kwargs"), args.get("confirm", False))

    if name == "rehearse":
        ref, db = args.get("ref", ""), args.get("db", "")
        if not ref or any(c.isspace() for c in ref) or ".." in ref:
            return False, f"invalid ref: {ref!r}"
        if not _valid_db(db):
            return False, f"invalid db {db!r}: must start with 'eot_', never 'eot_main', alnum/underscore only"
        rc, out, err = run(["sudo", "-n", REHEARSE_SCRIPT, ref, db], timeout=180)
        return rc == 0, (out + ("\n" + err if err else "")).strip()[-6000:]

    if name == "rehearse_stop":
        db = args.get("db", "")
        if not _valid_db(db):
            return False, f"invalid db {db!r}: must start with 'eot_', never 'eot_main'"
        rc, out, err = run(["sudo", "-n", REHEARSE_STOP_SCRIPT, db], timeout=30)
        return rc == 0, (out + ("\n" + err if err else "")).strip()

    if name == "clone_user":
        db = args.get("db", "")
        if not _valid_db(db):
            return False, f"invalid db {db!r}: accounts are never created on eot_main"
        rc, out, err = run(["sudo", "-n", CLONE_USER_SCRIPT, db], timeout=30)
        text = (out + ("\n" + err if err else "")).strip()
        return (rc == 0 and "EOT_CLONE_LOGIN=" in text), text

    if name == "audit":
        base = CLONE_ODOO if args.get("clone") else LOCAL_ODOO
        paths = args.get("paths") or ["/"]
        widths = args.get("widths") or [1280, 375]
        # snap chromium needs a writable, non-root HOME for its own confined
        # profile dirs - the systemd service sets none, so give it one here
        # rather than in the shared `run()` helper (nothing else needs it).
        env = dict(os.environ, HOME="/opt/eot-mcp/browser", XDG_CACHE_HOME="/opt/eot-mcp/browser/.cache")
        try:
            p = subprocess.run(
                [BROWSER_PY, __file__, "--audit-worker", base, json.dumps(paths), json.dumps(widths),
                 args.get("login") or "", args.get("password") or ""],
                capture_output=True, text=True, timeout=200, env=env,
            )
            rc, out, err = p.returncode, p.stdout, p.stderr
        except subprocess.TimeoutExpired:
            rc, out, err = -1, "", "audit timed out after 200s - try fewer paths/widths"
        return rc == 0, (out + ("\n" + err if err and rc != 0 else "")).strip()[-6000:]

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
    if len(sys.argv) > 1 and sys.argv[1] == "--audit-worker":
        # Re-exec of this file under BROWSER_PY (the venv with playwright
        # installed) - the main service runs under the bare system python3,
        # which doesn't have it. See call_tool's "audit" branch.
        _, _, base, paths_json, widths_json, login, password = sys.argv
        ok, text = audit_pages(json.loads(paths_json), json.loads(widths_json), base, login or None, password or None)
        print(text)
        sys.exit(0 if ok else 1)
    port = int(os.environ.get("MCP_PORT", "8091"))
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
