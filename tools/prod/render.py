#!/usr/bin/env python3
"""Render pages ON eot-odoo-prod and report only what matters.

Runs with prod's Odoo venv (requests available), fed over ssh stdin by
`eot render`. Talks to 127.0.0.1:<port> with Host www.eot.ir, fa_IR.

  render.py [--port 8069|8070] [--portal] [--outline N] URL...

Per URL: HTTP status, <title>, traceback flag, leftover English UI text
(scripts/styles/options removed; emails/urls ignored), and with --outline N
a compact class tree of #wrap (depth N) instead of raw HTML.

--portal signs in as the clone-only portal user (EOT_CLONE_LOGIN /
EOT_CLONE_PASSWORD env, set by `eot`), and is refused on port 8069 (live):
accounts are never created or used on the live database.
"""
import os
import re
import sys
from html import unescape
from html.parser import HTMLParser

import requests

args = sys.argv[1:]
port, portal, outline, sitemap, quiet = "8069", False, 0, False, False
while args and args[0].startswith("--"):
    a = args.pop(0)
    if a == "--port":
        port = args.pop(0)
    elif a == "--portal":
        portal = True
    elif a == "--outline":
        outline = int(args.pop(0))
    elif a == "--sitemap":   # route sweep: every sitemap URL + the system pages below
        sitemap = True
    elif a == "--quiet":     # print only URLs with a problem (non-200, traceback, English)
        quiet = True
# Pages that are not in the sitemap but visitors reach (auth, search, errors).
# /web/signup is deliberately absent: website 1 is invite-only (b2b), so it 404s.
SYSTEM = ["/web/login", "/web/reset_password", "/my", "/website/search?search=%D8%AF%D8%B1%D9%85%D8%A7%D9%86",
          "/this-page-does-not-exist", "/contactus", "/about"]
PORTAL = ["/my", "/my/home", "/my/account", "/my/addresses", "/my/security", "/my/conversations"]
if portal and port == "8069":
    sys.exit("!! --portal is only allowed on a rehearsal clone (--port 8070), never on live")

B = "http://127.0.0.1:" + port
H = {"Host": "www.eot.ir"}
s = requests.Session()
s.cookies.set("frontend_lang", "fa_IR")

if portal:
    login, pw = os.environ.get("EOT_CLONE_LOGIN"), os.environ.get("EOT_CLONE_PASSWORD")
    if not (login and pw):
        sys.exit("!! no clone user: run `eot clone-user DB` first")
    r = s.get(B + "/web/login", headers=H)
    tok = re.search(r'name="csrf_token" value="([^"]+)', r.text).group(1)
    r = s.post(B + "/web/login", headers=H, data={"csrf_token": tok, "login": login, "password": pw, "redirect": "/my"})
    print("signed in:", "yes" if "/my" in r.url else "NO (%s)" % r.url.replace(B, ""))

IGNORE = re.compile(r"@|https?:|www\.|\.ir\b|rehearsal\.invalid")


class Outline(HTMLParser):
    VOID = {"br", "img", "input", "meta", "link", "hr", "source"}

    def __init__(self, depth):
        super().__init__()
        self.depth, self.d, self.on, self.skip, self.out = depth, 0, False, 0, []

    def handle_starttag(self, t, a):
        a = dict(a)
        if a.get("id") == "wrap":
            self.on, self.d = True, 0
        if not self.on:
            return
        if t in ("svg", "script", "style"):
            self.skip += 1
        if not self.skip and self.d <= self.depth:
            cls = "".join("." + c for c in (a.get("class") or "").split()[:4])
            self.out.append("  " * self.d + "<" + t + ("#" + a["id"] if a.get("id") else "") + cls + ">")
        if t not in self.VOID:
            self.d += 1

    def handle_endtag(self, t):
        if not self.on or t in self.VOID:
            return
        self.d -= 1
        if t in ("svg", "script", "style"):
            self.skip -= 1
        if self.d < 0:
            self.on = False

    def handle_data(self, x):
        x = re.sub(r"\s+", " ", x).strip()
        if self.on and x and not self.skip and self.d <= self.depth + 1:
            self.out.append("  " * self.d + '"' + x[:50] + '"')


if sitemap:
    sm = s.get(B + "/sitemap.xml", headers=H).text
    locs = re.findall(r"<loc>(.*?)</loc>", sm)
    subs = [l for l in locs if l.endswith(".xml")]  # sitemap index -> child sitemaps
    for sub in subs:
        locs += re.findall(r"<loc>(.*?)</loc>", s.get(B + re.sub(r"^https?://[^/]+", "", sub), headers=H).text)
    paths = [re.sub(r"^https?://[^/]+", "", l) for l in locs if not l.endswith(".xml")]
    args = list(dict.fromkeys(paths + SYSTEM + (PORTAL if portal else []) + args))

# 404 is the expected answer for the deliberately missing page.
EXPECT = {"/this-page-does-not-exist": 404}
bad = 0
for url in args:
    r = s.get(B + url, headers=H, allow_redirects=True)
    html = r.text
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    body = re.sub(r"<(script|style|svg|option|template)\b.*?</\1>", " ", html, flags=re.S | re.I)
    m = re.search(r'<div id="wrapwrap".*', body, re.S)
    texts = [unescape(t).strip() for t in re.split(r"<[^>]+>", m.group(0) if m else body)]
    en = sorted({t[:50] for t in texts if re.search(r"[A-Za-z]{3,}", t) and not IGNORE.search(t) and len(t) < 120})
    trace = "Traceback" in html or "Internal Server Error" in html
    status_bad = r.status_code != EXPECT.get(url, 200)
    ttl = unescape(title.group(1).strip()) if title else ""
    title_en = bool(re.search(r"[A-Za-z]{3,}", ttl.split("|")[0]))  # view-name fallback, e.g. "Page Not Found"
    if quiet and url not in SYSTEM + PORTAL:
        en = []  # content pages carry deliberate English (article keywords); only UI pages are judged
    if quiet and not (trace or status_bad or en or title_en):
        continue
    bad += bool(trace or status_bad or title_en)
    print("%s %s%s%s | %s" % (r.status_code, url, "  TRACEBACK" if trace else "", "  ENGLISH-TITLE" if title_en else "", ttl or "-"))
    if en:
        print("   english:", "; ".join(en[:12]))
    if outline:
        o = Outline(outline)
        o.feed(html)
        print("\n".join("   " + line for line in o.out[:120]))
if len(args) > 1:
    print("-- %d urls, %d broken (non-200, traceback or English title)" % (len(args), bad))
