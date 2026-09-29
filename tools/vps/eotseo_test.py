#!/usr/bin/env python3
"""SEO acceptance test for eot.ir (milestone 9, docs/seo_runbook.md).

Runs ON PROD (copied there by `eot seo test`), against live or a rehearsal clone:
    python3 eotseo_test.py https://www.eot.ir
    python3 eotseo_test.py http://127.0.0.1:8070     (clone; nginx headers are faked)
Prints ok/FAIL lines and a final "RESULT: N failures". Standard library only.
"""
import collections
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else 'https://www.eot.ir'
CLONE = '127.0.0.1' in BASE
HDR = {'User-Agent': 'Mozilla/5.0 (compatible; Googlebot/2.1; eot-seo)'}
if CLONE:
    HDR.update({'Host': 'www.eot.ir', 'X-Forwarded-Host': 'www.eot.ir',
                'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '10.0.0.1'})
FAIL = []


def enc(p):
    s = urllib.parse.urlsplit(p)
    return urllib.parse.urlunsplit(('', '', urllib.parse.quote(urllib.parse.unquote(s.path)), s.query, ''))


class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


OP = urllib.request.build_opener(NR)


def get(path):
    try:
        r = OP.open(urllib.request.Request(BASE + enc(path), headers=HDR), timeout=60)
        return r.status, '', r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        loc = urllib.parse.unquote(e.headers.get('Location', '') or '')
        return e.code, re.sub(r'^https?://[^/]+', '', loc), ''


def chain(path, n=5):
    hops = []
    for _ in range(n):
        st, loc, _b = get(path)
        hops.append(st)
        if st in (301, 302, 303, 307, 308) and loc:
            path = loc
        else:
            return hops, path, st
    return hops, path, st


def check(name, ok, detail=''):
    print(('ok   ' if ok else 'FAIL ') + name + ('  ' + detail if detail else ''), flush=True)
    if not ok:
        FAIL.append(name)


# 1. robots + sitemap ---------------------------------------------------------
st, _, robots = get('/robots.txt')
check('robots Sitemap is https', 'Sitemap: https://www.eot.ir/sitemap.xml' in robots,
      str([l for l in robots.splitlines() if l.startswith('Sitemap')]))
st, _, sm = get('/sitemap.xml')
locs = re.findall(r'<loc>(.*?)</loc>', sm)
paths = [urllib.parse.unquote(urllib.parse.urlsplit(l).path) for l in locs]
check('sitemap has URLs', len(locs) > 900, '%d locs' % len(locs))
check('sitemap all https://www.eot.ir', all(l.startswith('https://www.eot.ir/') for l in locs),
      str(collections.Counter('/'.join(l.split('/')[:3]) for l in locs)))
check('sitemap has no feeds', not any(p.endswith('/feed') for p in paths), str(sum(p.endswith('/feed') for p in paths)))
marks = [p for p in paths if re.search('[ً-ٰٟـءأإؤئۀةيك]', p)]
check('slugs: no diacritics / hamza / Arabic letter forms', not marks, ' | '.join(marks[:3]))
numbered = [p for p in paths if re.search(r'/\d+-[^\d]', p)]
print('info slugs starting with a number (author sub-section numbers, kept):', len(numbered))


# 2. one page per template ----------------------------------------------------
def page(path):
    st, loc, b = get(path)
    head = b.split('</head>')[0]
    canon = re.findall(r'<link\s+rel="canonical"\s+href="([^"]*)"', head)
    desc = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', head)
    og = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', head)
    title = re.search(r'<title[^>]*>(.*?)</title>', head, re.S)
    types = []
    for x in re.findall(r'<script[^>]*ld\+json[^>]*>(.*?)</script>', b, re.S):
        try:
            j = json.loads(x)
            types += [g.get('@type') for g in j.get('@graph', [j])]
        except Exception as e:
            types.append('INVALID:%s' % e)
    return {'st': st, 'canon': urllib.parse.unquote(canon[0]) if canon else '', 'desc': desc.group(1) if desc else '',
            'og': og.group(1) if og else '', 'types': types, 'title': title.group(1).strip() if title else '', 'body': b}


samples = {'home': '/', 'books': '/کتب', 'articles': '/مقالات', 'glossary': '/فرهنگنامه'}
for p in paths:
    k = ('book' if p.startswith('/کتب/') and p.count('/') == 2 else 'chapter' if p.startswith('/کتب/')
         else 'article' if p.startswith('/مقالات/') else 'term' if p.startswith('/فرهنگنامه/') else None)
    if k and k not in samples:
        samples[k] = p
want = {'home': {'Organization', 'WebSite'}, 'books': {'CollectionPage', 'BreadcrumbList'},
        'articles': {'CollectionPage', 'BreadcrumbList'}, 'glossary': {'DefinedTermSet', 'BreadcrumbList'},
        'book': {'Book', 'BreadcrumbList'}, 'chapter': {'Article', 'BreadcrumbList'},
        'article': {'Article', 'BreadcrumbList'}, 'term': {'DefinedTerm', 'DefinedTermSet', 'BreadcrumbList'}}
for k, p in samples.items():
    r = page(p)
    check('%-8s 200' % k, r['st'] == 200, p)
    check('%-8s canonical self' % k, r['canon'] == 'https://www.eot.ir' + p, r['canon'][-60:])
    check('%-8s meta description' % k, len(r['desc']) >= 50, str(len(r['desc'])))
    check('%-8s og:image real' % k, r['og'].startswith('https://www.eot.ir/web/image/'), r['og'][:70])
    check('%-8s JSON-LD types' % k, want[k] <= set(r['types']) and 'Organization' in r['types'], str(r['types']))
    check('%-8s title <= 70' % k, len(r['title']) <= 70, '%d %s' % (len(r['title']), r['title'][:60]))
    if k == 'chapter':
        check('chapter byline', 'از کتاب' in r['body'])

# 3. old URLs land on the RIGHT page (or 404) -----------------------------------
CONSULT = r'^/مشاوره-روانشناسی-آنلاین$'
cases = [
    ('/blog/resources-20/انواع-هوش-ماهیت-تعاملی-هوش-های-سه-گانه-2177', r'^/مقالات/انواع-هوش-ماهیت-تعاملی'),
    ('/blog/glossary-15/حمایت-معنوی-2013', r'^/فرهنگنامه/حمایت-معنوی-\d+$'),
    ('/blog/resources-20/هویت-فردی-2886', 404),
    ('/blog/resources-20/page/7', r'^/مقالات$'),
    ('/book-session', CONSULT), ('/book-session/dr-kazemi-haghighi', CONSULT),
    ('/psychology-clinic', CONSULT), ('/khdh-nwbt-mshwrh', CONSULT), ('/appointment/4', CONSULT),
    ('/drkazemi', r'^/دکتر-ناصرالدین-کاظمی-حقیقی$'),
    ('/contact', r'^/contactus$'),
    ('/روانشناسی-فرهنگی-بررسی-تعامل-انسان-با-فرهنگ', r'^/کتب/روانشناسی-فرهنگی$'),
    ('/blog/خلاقیت-31', r'^/کتب/خلاقیت$'),
    ('/blog/هیجان-اندیشه-22', r'^/کتب/هیجان-اندیشه$'),
    ('/blog/خلاقیت-هوش-و-تیزهوشی-32', r'^/کتب/خلاقیت-هوش-و-تیزهوشی$'),
    ('/blog/استعداد-ریاضی-43', r'^/کتب/استعداد-ریاضی$'),
    ('/shop/category/دورههای-تخصصی-2', r'^/یادگیری-خودیار-روانشناسی$'),
    ('/مقالات/هیجان-اندیشه-و-شخصیّت-1990', r'^/مقالات/هیجان-اندیشه-و-شخصیت-1990$'),
    ('/کتب/روانشناسي-انتظار', r'^/کتب/روانشناسی-انتظار$'),
    ('/en', r'^/$'),
]
for src, exp in cases:
    hops, final, st = chain(src)
    if exp == 404:
        check('redirect %s' % src[:55], st == 404, str(hops))
    else:
        check('redirect %s' % src[:55], st == 200 and re.search(exp, final) is not None and len(hops) <= 3,
              '%s -> %s' % (hops, final[:60]))

print('\nRESULT: %d failures' % len(FAIL), FAIL[:10])
