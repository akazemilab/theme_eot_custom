#!/usr/bin/env python3
"""Persian URL quality check for eot.ir (docs/seo_runbook.md).

    eot seo urls            -> detached job 'seo-urls', verdict lines + RESULT

What it checks, all against the live sitemap (standard library only):
  1. shape    - length (decoded / percent-encoded), trailing id, clean letter forms,
                Latin or mixed-script slugs, duplicate slug text under one parent
  2. meaning  - the slug text says what the page says (token overlap with the <title>
                recorded by `eot seo sweep`, if that file exists)
  3. variants - what a person or another site might type/link: Arabic-keyboard ي/ك,
                half-space instead of hyphen, space, trailing slash, lower-case
                percent-encoding, NFD text, wrong slug with the right id, http:// and
                apex host. Each must end on the canonical URL (<=2 hops) or 404,
                never a 200 on a second address.
  4. links    - every internal link on the section pages + a sample of items points
                straight at a 200 canonical URL (no redirect hop, no 404).
Prints ok/WARN/FAIL lines and "RESULT: N failures, M warnings".
"""
import collections
import concurrent.futures as cf
import csv
import html
import os
import random
import re
import statistics
import sys
import unicodedata
import urllib.parse
import urllib.request

BASE = 'https://www.eot.ir'
HDR = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; eot-seo)', 'Accept-Language': 'fa'}
SWEEP = '/root/eot-jobs/seo_sweep.tsv'
PER_TEMPLATE = 4
random.seed(7)
FAIL, WARN = [], []


def say(level, name, detail=''):
    print('%-4s %s%s' % (level, name, ('  ' + detail) if detail else ''), flush=True)
    {'FAIL': FAIL, 'WARN': WARN}.get(level, []).append(name)


class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OP = urllib.request.build_opener(NR)


def raw_get(url):
    """url must already be ASCII (percent-encoded). Returns status, Location, body."""
    try:
        r = OP.open(urllib.request.Request(url, headers=HDR), timeout=40)
        return r.status, '', r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Location', '') or '', ''
    except Exception as e:  # network trouble is reported, not fatal
        return 'ERR:' + type(e).__name__, '', ''


def q(path):
    return urllib.parse.quote(path, safe='/-_.~')


def chain(url, n=5):
    """Follow redirects; returns (hops, final_status, final_decoded_url)."""
    hops = 0
    for _ in range(n):
        st, loc, body = raw_get(url)
        if isinstance(st, int) and 300 <= st < 400 and loc:
            url = urllib.parse.urljoin(url, loc)
            hops += 1
            continue
        return hops, st, urllib.parse.unquote(url), body
    return hops, 'LOOP', urllib.parse.unquote(url), ''


def template(p):
    parts = p.strip('/').split('/')
    if p == '/':
        return 'home'
    if parts[0] == 'کتب':
        return {1: 'books', 2: 'book', 3: 'chapter'}.get(len(parts), 'other')
    if parts[0] == 'مقالات':
        return 'articles' if len(parts) == 1 else 'article'
    if parts[0] == 'فرهنگنامه':
        return 'glossary' if len(parts) == 1 else 'term'
    return 'page'


TOKEN_SPLIT = re.compile(r'[\s\-_:،,.؛;()«»"\'!?؟/|‌]+')
STOP = {'و', 'در', 'به', 'از', 'با', 'یک', 'این', 'برای', 'های', 'ها', 'که', 'را', 'بر', 'هیجان', 'اندیشه'}


def tokens(s):
    s = unicodedata.normalize('NFC', s or '')
    s = re.sub('[ً-ٰٟـ]', '', s).replace('ي', 'ی').replace('ك', 'ک').replace('آ', 'ا').replace('ء', '').lower()
    return {t for t in TOKEN_SPLIT.split(s) if len(t) > 1 and not t.isdigit() and t not in STOP}


def main():
    st, _, sm = raw_get(BASE + '/sitemap.xml')
    locs = re.findall(r'<loc>(.*?)</loc>', sm)
    paths = [urllib.parse.unquote(urllib.parse.urlsplit(l).path) for l in locs]
    by = collections.defaultdict(list)
    for p in paths:
        by[template(p)].append(p)
    print('sitemap', len(paths), 'URLs:', ', '.join('%s %d' % (k, len(v)) for k, v in sorted(by.items())), flush=True)

    # 1. shape ------------------------------------------------------------------
    dec = [len(p) for p in paths]
    encl = [len(q(p)) for p in paths]
    print('info length decoded: median %d, max %d | percent-encoded: median %d, p95 %d, max %d' % (
        statistics.median(dec), max(dec), statistics.median(encl), sorted(encl)[int(len(encl) * .95)], max(encl)))
    very_long = [p for p in paths if len(q(p)) > 1000]
    say('ok' if not very_long else 'WARN', 'no URL over 1000 encoded chars', str(len(very_long)))
    items = [p for p in paths if template(p) in ('chapter', 'article', 'term')]
    no_id = [p for p in items if not re.search(r'-\d+$', p)]
    say('ok' if not no_id else 'FAIL', 'every chapter/article/term slug ends in its record id', ' | '.join(no_id[:3]))
    forms = [p for p in paths if re.search('[ً-ٰٟـءأإؤئۀةيك‌]', p)]
    say('ok' if not forms else 'FAIL', 'no diacritics, hamza forms, Arabic ي/ك or half-spaces in slugs', ' | '.join(forms[:3]))
    latin = [p for p in paths if template(p) in ('chapter', 'article', 'term', 'book') and re.search('[A-Za-z]', p.split('/')[-1])]
    print('info slugs containing Latin letters (English terms in titles):', len(latin), ' | '.join(latin[:2]))
    doubles = [p for p in paths if '--' in p or p.endswith('-') or '/-' in p]
    say('ok' if not doubles else 'WARN', 'no empty slug parts (--, leading/trailing hyphen)', ' | '.join(doubles[:3]))
    parent = collections.Counter()
    for p in items:
        head, slug = p.rsplit('/', 1)
        parent[(head, re.sub(r'-\d+$', '', slug))] += 1
    dup = [(h + '/' + s) for (h, s), c in parent.items() if c > 1]
    say('ok' if not dup else 'WARN', 'no two items share slug text under one parent (the id still keeps them apart)',
        '%d, e.g. %s' % (len(dup), ' | '.join(dup[:2])) if dup else '')

    # 2. meaning ------------------------------------------------------------------
    if os.path.exists(SWEEP):
        titles = {}
        with open(SWEEP) as f:
            for r in csv.DictReader(f, delimiter='\t'):
                titles[urllib.parse.unquote(urllib.parse.urlsplit(r['url']).path)] = r.get('title', '')
        weak = []
        for p in items + by.get('book', []):
            t = titles.get(p)
            if not t:
                continue
            s = tokens(re.sub(r'-\d+$', '', p.rsplit('/', 1)[1]))
            tt = tokens(t)
            if s and len(s & tt) / len(s) < 0.6:
                weak.append((p, t))
        say('ok' if len(weak) <= len(items) * .02 else 'WARN', 'slug text matches the page title (>=60% of slug words)',
            '%d weak: %s' % (len(weak), ' | '.join('%s ~ %s' % (a.rsplit('/', 1)[1][:30], b[:30]) for a, b in weak[:3])))
    else:
        print('info no %s yet (run `eot seo sweep` first) - slug/title check skipped' % SWEEP)

    # 3. variants -----------------------------------------------------------------
    cases = []
    for k in ('book', 'chapter', 'article', 'term'):
        for p in random.sample(by.get(k, []), min(PER_TEMPLATE, len(by.get(k, [])))):
            canon = BASE + q(p)
            v = {
                'arabic ي/ك': p.replace('ی', 'ي').replace('ک', 'ك'),
                'half-space for hyphen': p.replace('-', '‌', 1),
                'space for hyphen': p.replace('-', ' ', 1),
                'trailing slash': p + '/',
                'NFD text': unicodedata.normalize('NFD', p),
            }
            for name, vp in v.items():
                if vp != p:
                    cases.append((k, name, BASE + q(vp), canon, p))
            cases.append((k, 'lower-case %xx', BASE + q(p).lower(), canon, p))
            cases.append((k, 'http + apex host', 'http://eot.ir' + q(p), canon, p))
            m = re.search(r'-(\d+)$', p)
            if m:
                cases.append((k, 'wrong slug, right id', BASE + q(p.rsplit('/', 1)[0] + '/x-' + m.group(1)), canon, p))
    results = collections.defaultdict(collections.Counter)
    bad = []

    def run(c):
        k, name, url, canon, p = c
        hops, st, final, _ = chain(url)
        good_redirect = st == 200 and final == urllib.parse.unquote(canon)
        if hops == 0 and st == 200 and final != urllib.parse.unquote(canon):
            verdict = 'DUPLICATE'          # a second address serving the page
        elif good_redirect and hops <= 2:
            verdict = 'ok'
        elif good_redirect:
            verdict = 'ok-long'
        elif st == 404:
            verdict = '404'
        else:
            verdict = 'WRONG'
        return name, verdict, (k, name, st, hops, p, final)

    with cf.ThreadPoolExecutor(4) as ex:
        for name, verdict, detail in ex.map(run, cases):
            results[name][verdict] += 1
            if verdict != 'ok':
                bad.append((verdict, detail))
    for name, c in results.items():
        level = 'FAIL' if c['DUPLICATE'] or c['WRONG'] else 'WARN' if c['404'] or c['ok-long'] else 'ok'
        say(level, 'variant %-22s' % name, dict(c).__repr__())
    by_kind = collections.Counter((v, d[1], d[0]) for v, d in bad)
    for (v, name, k), n in sorted(by_kind.items()):
        print('     %-9s %-22s on %-8s x%d' % (v, name, k, n))
    for verdict, (k, name, st, hops, p, final) in [b for b in bad if b[0] != '404'][:4]:
        print('     %s %s %s: %s hops=%s -> %s' % (verdict, k, name, st, hops, final.replace(BASE, '')[:70]))

    # 4. internal links -----------------------------------------------------------
    sitemap_set = set(paths)
    pages = ['/', '/کتب', '/مقالات', '/فرهنگنامه']
    for k in ('book', 'chapter', 'article', 'term'):
        pages += random.sample(by.get(k, []), min(2, len(by.get(k, []))))
    hrefs = collections.Counter()
    for p in pages:
        _, _, body = raw_get(BASE + q(p))
        for h in re.findall(r'<a\b[^>]*\shref="([^"#?]+)', body):
            h = html.unescape(h)
            if h.startswith(BASE):
                h = h[len(BASE):]
            if h.startswith('/') and not h.startswith(('//', '/web/', '/website/')):
                hrefs[urllib.parse.unquote(h)] += 1
    link_bad = collections.Counter()
    ex_bad = []

    def probe(h):
        st, loc, _ = raw_get(BASE + q(h))
        return h, st, urllib.parse.unquote(loc)

    with cf.ThreadPoolExecutor(4) as ex:
        for h, st, loc in ex.map(probe, list(hrefs)):
            if st == 200:
                continue
            kind = 'redirect' if isinstance(st, int) and 300 <= st < 400 else str(st)
            link_bad[kind] += 1
            ex_bad.append('%s %s -> %s' % (st, h[:50], loc.replace(BASE, '')[:50]))
    print('info internal links: %d unique targets from %d pages; %d are in the sitemap' % (
        len(hrefs), len(pages), sum(1 for h in hrefs if h in sitemap_set)))
    say('ok' if not link_bad else ('FAIL' if any(k.startswith(('4', '5')) for k in link_bad) else 'WARN'),
        'internal links go straight to a 200 page', '%s %s' % (dict(link_bad), ' | '.join(ex_bad[:4])) if link_bad else '')

    print('RESULT: %d failures, %d warnings' % (len(FAIL), len(WARN)))


main()
