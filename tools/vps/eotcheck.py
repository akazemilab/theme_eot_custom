#!/usr/bin/env python3
"""Compact, token-cheap health checks for the eot.ir website (website 1).

Every command prints short lines only - the point is to do the heavy work
here on the VPS and return a verdict, not raw HTML/CSS.

  check [URL]         page + every CSS/JS/image asset: status, type, and
                      whether each stylesheet actually PARSES (rule count).
                      Catches "CSS loads 200 but browser uses 0 rules".
  placeholders [BASE] crawl the sitemap and grep rendered pages for demo
                      placeholders (555-555, yourcompany, lorem ipsum, ...);
                      also lists sitemap pages that don't return 200.
  links [URL]         every internal link on a page -> HTTP status; lists
                      only the broken ones (dead links, unpublished pages).
  text URL [N]        visible text of a page (first N chars, default 1500).
"""
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

import requests
import tinycss2

BASE = "https://www.eot.ir"
UA = "Mozilla/5.0 (eot-tools check)"
# fa_IR is the site's default language; force it so we see what visitors see.
COOKIES = {"frontend_lang": "fa_IR"}
TIMEOUT = 30

PLACEHOLDER_RE = re.compile(
    r"555-555-\d{3,4}|\+1 ?\(?650\)?[\d \-]{6,}|info@yourcompany|yourcompany@"
    r"|yourcompany\.example|@example\.com|lorem ipsum|\bMy Company\b"
    r"|\bYour Company\b|\bYourCompany\b|Company Name|\[YOUR[^\]]*\]",
    re.I,
)
DEFAULT_RE = re.compile(r"Powered by\s*<[^>]*>?\s*Odoo|Create a free website", re.I)

S = requests.Session()
S.headers["User-Agent"] = UA
S.cookies.update(COOKIES)


def get(url):
    return S.get(url, timeout=TIMEOUT, allow_redirects=True)


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.css, self.js, self.img = [], [], []
        self.lang = self.dir = None
        self.marker = False

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "html":
            self.lang, self.dir = a.get("lang"), a.get("dir")
        elif tag == "link" and "stylesheet" in (a.get("rel") or ""):
            self.css.append(a.get("href"))
        elif tag == "script" and (a.get("src") or a.get("data-src")):
            self.js.append(a.get("src") or a.get("data-src"))
        elif tag == "img" and a.get("src") and not a["src"].startswith("data:"):
            self.img.append(a.get("src"))
        elif tag == "meta" and a.get("name") == "eot-theme":
            self.marker = True


def css_verdict(text):
    rules = tinycss2.parse_stylesheet(text, skip_comments=True, skip_whitespace=True)
    ok = [r for r in rules if r.type in ("qualified-rule", "at-rule")]
    errs = [r for r in rules if r.type == "error"]
    msg = f"{len(ok)} rules, {len(errs)} parse errors"
    if errs:
        msg += f"; first error: {errs[0].message!r}"
    if len(ok) < 5 and len(text) > 10000:
        msg += f" !! BROKEN (big file, ~no rules). starts: {text[:120]!r}"
    return msg


def cmd_check(url=BASE + "/"):
    r = get(url)
    p = Assets()
    p.feed(r.text)
    print(f"PAGE {r.status_code} {r.url} lang={p.lang} dir={p.dir} "
          f"marker={'yes' if p.marker else 'NO'} {len(r.text)//1024}KB")
    bad = 0
    for kind, urls in (("css", p.css), ("js", p.js), ("img", p.img)):
        for u in dict.fromkeys(urls):
            full = urljoin(r.url, u)
            try:
                a = get(full)
            except Exception as e:  # noqa: BLE001
                print(f"  {kind} ERR {full} {e}")
                bad += 1
                continue
            ctype = a.headers.get("content-type", "").split(";")[0]
            line = f"  {kind} {a.status_code} {ctype} {len(a.content)//1024}KB {urlparse(full).path[-60:]}"
            if kind == "css" and a.ok and urlparse(full).netloc == urlparse(r.url).netloc:
                line += " | " + css_verdict(a.text)
            if not a.ok:
                bad += 1
            print(line)
    print("RESULT", "OK" if bad == 0 else f"{bad} FAILED ASSET(S)")


def sitemap_urls(base, limit=200):
    r = get(base.rstrip("/") + "/sitemap.xml")
    urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
    # Odoo sitemaps can be an index of sub-sitemaps.
    out = []
    for u in urls:
        if u.endswith(".xml"):
            out += re.findall(r"<loc>([^<]+)</loc>", get(u).text)
        else:
            out.append(u)
    return list(dict.fromkeys(out))[:limit]


def cmd_placeholders(base=BASE):
    urls = sitemap_urls(base)
    base_host = urlparse(base).netloc
    print(f"scanning {len(urls)} pages")
    hits = {}
    defaults = set()
    broken = []
    for u in urls:
        u = u.replace(urlparse(u).netloc, base_host, 1)
        try:
            resp = get(u)
        except Exception as e:  # noqa: BLE001
            print(f"  ERR {u} {e}")
            continue
        if resp.status_code != 200:
            broken.append(f"{resp.status_code} {unquote(urlparse(u).path)}")
        html = resp.text
        body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        for m in set(x.group(0) for x in PLACEHOLDER_RE.finditer(body)):
            hits.setdefault(m, []).append(urlparse(u).path)
        if DEFAULT_RE.search(body):
            defaults.add(urlparse(u).path)
    if not hits:
        print("NO PLACEHOLDERS FOUND")
    for m, pages in sorted(hits.items(), key=lambda kv: -len(kv[1])):
        print(f"  {m!r} on {len(pages)} page(s): {', '.join(pages[:5])}{' ...' if len(pages) > 5 else ''}")
    if defaults:
        print(f"  (Odoo default 'Powered by Odoo' footer on {len(defaults)} page(s))")
    if broken:
        print(f"BROKEN PAGES in sitemap ({len(broken)}):")
        for b in broken:
            print("  " + b)


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.out = []

    def handle_starttag(self, tag, a):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg") and self.skip:
            self.skip -= 1

    def handle_data(self, d):
        if not self.skip and d.strip():
            self.out.append(d.strip())


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, a):
        if tag == "a":
            h = dict(a).get("href")
            if h and not h.startswith(("#", "mailto:", "tel:", "javascript:")):
                self.hrefs.append(h)


def cmd_links(url=BASE + "/"):
    page = get(url)
    p = Links()
    p.feed(page.text)
    host = urlparse(page.url).netloc
    targets = [urljoin(page.url, h).split("#")[0] for h in p.hrefs]
    targets = [t for t in dict.fromkeys(targets) if urlparse(t).netloc == host]
    bad = []
    for t in targets:
        try:
            code = S.head(t, timeout=TIMEOUT, allow_redirects=True).status_code
            if code == 405:
                code = get(t).status_code
        except Exception as e:  # noqa: BLE001
            code = f"ERR {e}"
        if code != 200:
            bad.append(f"  {code} {unquote(urlparse(t).path)}")
    print(f"{len(targets)} internal links on {unquote(urlparse(page.url).path)}: "
          + ("ALL OK" if not bad else f"{len(bad)} BROKEN"))
    print("\n".join(bad))


def cmd_text(url, n=1500):
    t = Text()
    t.feed(get(url).text)
    print(" | ".join(t.out)[: int(n)])


if __name__ == "__main__":
    cmds = {"check": cmd_check, "placeholders": cmd_placeholders, "links": cmd_links, "text": cmd_text}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]](*sys.argv[2:])
