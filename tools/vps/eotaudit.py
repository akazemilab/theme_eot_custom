#!/usr/bin/env python3
"""Headless design/quality audit on the VPS (replaces the browser pane for
milestone-8-style audits). Runs static/tools/eot_audit.js - the same file the
browser pane can import - inside each page and prints only problems.

  eotaudit.py [--base URL] [--widths 1280,375] [--login L --password P] PATH...
  eotaudit.py ... all          # every sitemap page + system pages

--base defaults to https://www.eot.ir (live, read-only). For a rehearsal
clone `eot audit --clone` opens an SSH tunnel to prod 127.0.0.1:8070 and
passes --base http://127.0.0.1:18070 (website 1 answers any host).
--login/--password (clone only, enforced by the eot wrapper) sign in first so
/my pages can be audited.

Browser: snap chromium (cdn.playwright.dev and Google storage are geo-blocked
for Iranian IPs; snapcraft is not). 1 GB RAM: one page at a time, images of
other origins blocked, the browser restarted every 15 pages.
"""
import json
import os
import re
import sys
import time

from playwright.sync_api import sync_playwright

CHROME = os.environ.get("EOT_CHROME", "/snap/chromium/current/usr/lib/chromium-browser/chrome")
JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "static", "tools", "eot_audit.js")
SYSTEM = ["/web/login", "/web/signup", "/web/reset_password", "/search?search=درمان", "/this-page-does-not-exist"]
PORTAL = ["/my", "/my/account", "/my/addresses", "/my/security"]

args = sys.argv[1:]
base, widths, login, password = "https://www.eot.ir", [1280, 375], None, None
while args and args[0].startswith("--"):
    a = args.pop(0)
    if a == "--base":
        base = args.pop(0).rstrip("/")
    elif a == "--widths":
        widths = [int(w) for w in args.pop(0).split(",")]
    elif a == "--login":
        login = args.pop(0)
    elif a == "--password":
        password = args.pop(0)
paths = args or ["/"]


def sitemap_paths(req):
    locs, todo = [], ["/sitemap.xml"]
    while todo:
        body = req.get(base + todo.pop()).text()
        for loc in re.findall(r"<loc>(.*?)</loc>", body):
            p = re.sub(r"^https?://[^/]+", "", loc)
            (todo if p.endswith(".xml") else locs).append(p)
    return locs


js = open(JS, encoding="utf-8").read()
t0 = time.time()
checked, bad = 0, 0
with sync_playwright() as pw:
    def launch():
        b = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"])
        ctx = b.new_context(locale="fa-IR")  # tunnel: website 1 is the only site, any host resolves to it
        ctx.add_cookies([{"name": "frontend_lang", "value": "fa_IR", "url": base}])
        if login:
            pg = ctx.new_page()
            pg.goto(base + "/web/login", wait_until="load")
            pg.fill("input[name=login]", login)
            pg.fill("input[name=password]", password)
            pg.click("form.oe_login_form button[type=submit]")
            pg.wait_for_load_state("load")
            print("signed in:", "yes" if "/my" in pg.url or "/odoo" in pg.url else "NO (%s)" % pg.url, flush=True)
            pg.close()
        return b, ctx

    browser, ctx = launch()
    if paths == ["all"]:
        paths = list(dict.fromkeys(sitemap_paths(ctx.request) + SYSTEM + (PORTAL if login else [])))
    for i, path in enumerate(paths):
        if i and i % 15 == 0:
            browser.close()
            browser, ctx = launch()
        for w in widths:
            pg = ctx.new_page()
            pg.set_viewport_size({"width": w, "height": 900})
            try:
                resp = pg.goto(base + path, wait_until="load", timeout=60000)
                pg.wait_for_timeout(400)
                pg.add_script_tag(content=js)
                res = pg.evaluate("eotAudit.page(window)")
                res["status"] = resp.status if resp else 0
            except Exception as e:  # keep going; report the page as broken
                res = {"url": path, "error": str(e).splitlines()[0][:160], "ok": False, "problems": {}}
            finally:
                pg.close()
            checked += 1
            expected = 404 if path == "/this-page-does-not-exist" else 200
            if res.get("status", expected) != expected:
                res["ok"] = False
                res["problems"]["status"] = res["status"]
            if not res.get("ok"):
                bad += 1
                print("%4d %s  %s" % (w, path, json.dumps(res.get("problems") or {"error": res.get("error")}, ensure_ascii=False)), flush=True)
    browser.close()
print("-- %d page-widths checked, %d with problems, %ds" % (checked, bad, time.time() - t0), flush=True)
sys.exit(1 if bad else 0)
