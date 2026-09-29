#!/usr/bin/env python3
"""SEO sweep of every eot.ir sitemap URL (docs/seo_runbook.md). Runs on the VPS:
    eot seo sweep            (detached; ~5 min for ~1,000 URLs, 4 threads)
Writes /root/eot-jobs/seo_sweep.tsv (one row per URL) and prints verdicts per
section: status, canonical == self, noindex, title length/duplicates, meta
description, h1 count, og:image, JSON-LD types, <img> alt/loading/size,
and Persian slug hygiene.
"""
import collections
import concurrent.futures as cf
import csv
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = next((a for a in sys.argv[1:] if a.startswith('http')), 'https://www.eot.ir')
OUT = '/root/eot-jobs/seo_sweep.tsv'
UA = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; eot-seo)', 'Accept-Language': 'fa'}


def enc(u):
    p = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(urllib.parse.unquote(p.path)), p.query, ''))


class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OP = urllib.request.build_opener(NR)


def fetch(u):
    try:
        r = OP.open(urllib.request.Request(enc(u), headers=UA), timeout=40)
        return r.status, dict(r.headers), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), ''
    except Exception as e:
        return 0, {}, type(e).__name__


def txt(s):
    return html.unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', '', s or ''))).strip()


def check(u):
    st, h, b = fetch(u)
    r = {'url': urllib.parse.unquote(u), 'status': st, 'location': urllib.parse.unquote(h.get('Location', ''))}
    if st != 200:
        return r
    head = b.split('</head>')[0]
    t = re.search(r'<title[^>]*>(.*?)</title>', head, re.S)
    d = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', head)
    c = re.findall(r'<link\s+rel="canonical"\s+href="([^"]*)"', head)
    og = dict(re.findall(r'<meta\s+property="og:(\w+)"\s+content="([^"]*)"', head))
    rob = ' '.join(re.findall(r'<meta\s+name="robots"\s+content="([^"]*)"', head)) + ' ' + h.get('X-Robots-Tag', '')
    types = []
    for x in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', b, re.S):
        try:
            j = json.loads(x)
            types += [g.get('@type') for g in j.get('@graph', [j])]
        except Exception:
            types.append('INVALID')
    body = b.split('<body', 1)[-1]
    imgs = re.findall(r'<img\b[^>]*>', body)
    canon = urllib.parse.unquote(c[0]) if c else ''
    title = txt(t.group(1)) if t else ''
    r.update({
        'canonical': canon, 'canon_self': canon == r['url'], 'robots': rob.strip(),
        'title': title, 'title_len': len(title), 'desc_len': len(html.unescape(d.group(1)).strip()) if d else 0,
        'h1': len(re.findall(r'<h1[\s>]', body)), 'og_image': og.get('image', ''),
        'jsonld': ','.join(str(x) for x in types), 'img': len(imgs),
        'img_noalt': sum(1 for i in imgs if not re.search(r'\salt=', i)),
        'img_nolazy': sum(1 for i in imgs if 'loading=' not in i),
        'img_nodim': sum(1 for i in imgs if not re.search(r'\swidth=', i)),
    })
    return r


def section(u):
    path = urllib.parse.urlsplit(u).path.strip('/')
    return path.split('/')[0] if '/' in path else 'page'


def main():
    sm = urllib.request.urlopen(urllib.request.Request(BASE + '/sitemap.xml', headers=UA), timeout=60).read().decode()
    locs = re.findall(r'<loc>(.*?)</loc>', sm)
    print('sitemap locs', len(locs), '| not https://www.eot.ir:', sum(not l.startswith('https://www.eot.ir/') for l in locs), flush=True)
    paths = [urllib.parse.unquote(urllib.parse.urlsplit(l).path) for l in locs]
    hyg = {
        'diacritics/hamza/Arabic forms': lambda p: re.search('[ً-ٰٟـءأإؤئۀةيك]', p),
        'half-space in URL': lambda p: '‌' in p,
        'feed URL': lambda p: p.endswith('/feed'),
        'encoded path > 300 chars': lambda p: len(urllib.parse.quote(p)) > 300,
    }
    for k, f in hyg.items():
        hits = [p for p in paths if f(p)]
        print('slugs %-32s %4d  %s' % (k, len(hits), ' | '.join(h[:50] for h in hits[:2])))
    rows = []
    t0 = time.time()
    with cf.ThreadPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(check, locs), 1):
            rows.append(r)
            if i % 200 == 0:
                print('done', i, int(time.time() - t0), 's', flush=True)
    keys = ['url', 'status', 'location', 'canonical', 'canon_self', 'robots', 'title', 'title_len', 'desc_len', 'h1',
            'og_image', 'jsonld', 'img', 'img_noalt', 'img_nolazy', 'img_nodim']
    with open(OUT, 'w') as f:
        w = csv.DictWriter(f, keys, delimiter='\t', extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r['status'] == 200]
    C = collections.Counter
    print('status', dict(C(r['status'] for r in rows)))
    print('non-200', [(r['url'][-50:], r['status']) for r in rows if r['status'] != 200][:8])
    print('canonical != self', sum(not r['canon_self'] for r in ok), '| noindex', sum('noindex' in r['robots'] for r in ok))
    by = collections.defaultdict(list)
    for r in ok:
        by[section(r['url'])].append(r)
    for k, rs in by.items():
        print('[%s] n=%d no_desc=%d title>60=%d h1!=1=%d bad_og=%d noalt=%d jsonld=%s' % (
            k, len(rs), sum(r['desc_len'] == 0 for r in rs), sum(r['title_len'] > 60 for r in rs),
            sum(r['h1'] != 1 for r in rs),
            sum(not r['og_image'].startswith(BASE + '/web/image/') for r in rs),
            sum(r['img_noalt'] for r in rs), dict(C(r['jsonld'] for r in rs).most_common(2))))
    dup = C(r['title'] for r in ok)
    print('duplicate titles', sum(1 for t, c in dup.items() if c > 1), [(t[:40], c) for t, c in dup.most_common(3) if c > 1])
    print('elapsed', int(time.time() - t0), 's ->', OUT)


main()
