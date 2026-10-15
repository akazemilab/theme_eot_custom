"""Docx->clean HTML + SEO fields for eot.ir articles (blog 46). Content is never reworded:
only typography/whitespace/structure change, and a canonical-text comparison proves it.

Usage (any machine with pandoc + python3-bs4 + lxml):
  1. put a01.docx, a02.docx ... in DIR/in/
  2. for f in DIR/in/*.docx; do pandoc "$f" -t html -o DIR/html/$(basename "$f" .docx).html; done
  3. refresh DIR/terms.tsv (glossary id<TAB>term) with sql_query:
     select p.id, p.eot_title from blog_post p join blog_blog b on b.id=p.blog_id
     where b.eot_kind='glossary' and p.is_published
  4. optional DIR/topics.json {"1": "روان‌شناسی تعاملی", ...}; optional DIR/title_from_heading.json [1, ...]
     (articles whose title is the first heading, not the first block)
  5. python3 eot_article_prep.py DIR N   -> DIR/out/aNN.json + DIR/articles.csv (Odoo import, drafts)
Every row must print text-unchanged=True before importing. Runbook: docs/article_routine.md"""
import re, json, math, glob, os, csv, sys
from urllib.parse import quote
from bs4 import BeautifulSoup, NavigableString

S = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__))
N = int(sys.argv[2]) if len(sys.argv) > 2 else 14
ZW = '‌'
LET = 'آ-ی'
HARAKAT = re.compile('[ً-ٰٟ]')
TOK = re.compile('[؀-ۿ‌]+')
AR_DIG = str.maketrans('٠١٢٣٤٥٦٧٨٩', '۰۱۲۳۴۵۶۷۸۹')
FIX = {'تصمیمگیری': 'تصمیم' + ZW + 'گیری', 'تصمیمگیریها': 'تصمیم' + ZW + 'گیری' + ZW + 'ها',
       'بازداریهای': 'بازداری' + ZW + 'های', 'بازداریها': 'بازداری' + ZW + 'ها'}
FIX.update({'روانشناسی': 'روان' + ZW + 'شناسی', 'چشم انداز': 'چشم' + ZW + 'انداز',
            'هستی شناختی': 'هستی' + ZW + 'شناختی', 'وقوف مندی': 'وقوف' + ZW + 'مندی'})
GENERIC = {'توانایی', 'همراهی', 'هماهنگی', 'استقلال', 'مشارکت', 'مفهوم', 'نظریه', 'اندیشه', 'تجربه', 'ارزش', 'باور',
           'پویایی', 'رضایت', 'حمایت', 'تعهد', 'تعالی', 'بینش', 'نوآوری', 'استواری', 'تعادل', 'پشتیبانی', 'فرهنگ',
           'مکتب', 'مرجعیت', 'بالندگی', 'هیجان'}
_tp = os.path.join(S, 'topics.json')
TOPIC = {int(k): v for k, v in json.load(open(_tp, encoding='utf-8')).items()} if os.path.exists(_tp) else {}
_th = os.path.join(S, 'title_from_heading.json')
TITLE_FROM_HEADING = set(json.load(open(_th))) if os.path.exists(_th) else set()


def fold_tok(m):
    w = m.group(0)
    return w if HARAKAT.search(w) else w.replace('ي', 'ی').replace('ك', 'ک')


def norm(t, st):
    o = t
    t = TOK.sub(fold_tok, t); st['letters'] += sum(1 for a, b in zip(o, t) if a != b) if len(o) == len(t) else 0
    n = t.translate(AR_DIG); st['digits'] += sum(1 for a, b in zip(t, n) if a != b); t = n
    n = re.sub(r'[ \t ]{2,}', ' ', t); st['spaces'] += len(t) - len(n); t = n
    n = re.sub(r' +([،؛؟])', r'\1', t); st['punct'] += len(t) - len(n); t = n
    n = re.sub('([،؛؟])(?=[%s])' % LET, r'\1 ', t); st['punct'] += len(n) - len(t); t = n
    n, c = re.subn('(?<![%s%s])(ن?می) (?=[%s]{2,})' % (LET, ZW, LET), lambda m: m.group(1) + ZW, t); st['zwnj'] += c; t = n
    n, c = re.subn('(?<=[%s]) (ها|های|هایی)(?![%s])' % (LET, LET), lambda m: ZW + m.group(1), t); st['zwnj'] += c; t = n
    for k, v in FIX.items():
        if k in t:
            st['words'] += t.count(k); t = t.replace(k, v)
    return t


def canon(t):
    t = re.sub(r'[\s‌‏‎ ]+', '', t).translate(AR_DIG)
    return t.replace('ي', 'ی').replace('ك', 'ک')


def slug(title):
    s = re.sub('[ً-ٰـ]', '', title).translate(str.maketrans({'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ة': 'ه', 'ۀ': 'ه'}))
    return re.sub(r'[\W_]+', '-', s, flags=re.U).strip('-').lower()


def termre(term):
    parts = [re.escape(p) for p in re.split('[ ' + ZW + ']', term) if p]
    return re.compile('(?<![%s%s])%s(?![%s%s])' % (LET, ZW, '[ %s]' % ZW and ('[ %s]' % ZW).join(parts), LET, ZW))


TERMS = []
for line in open(S + '/terms.tsv', encoding='utf-8'):
    if line.strip():
        i, t = line.rstrip('\n').split('\t'); TERMS.append((int(i), t, termre(t)))
TERMS.sort(key=lambda x: -len(x[1]))


def process(n):
    raw = open('%s/html/a%02d.html' % (S, n), encoding='utf-8').read()
    soup = BeautifulSoup(raw, 'lxml'); body = soup.body
    st = dict(letters=0, digits=0, spaces=0, punct=0, zwnj=0, words=0)
    notes = []
    for t in body.find_all(['img', 'figure']):
        t.decompose()
    for t in body.find_all(True):
        keep = {'href': t.get('href')} if t.name == 'a' and t.get('href') else {}
        if t.get('id') and t['id'].startswith('fn'):
            keep['id'] = t['id']  # footnote anchors must keep working
        t.attrs = keep
    for t in body.find_all('span'):
        t.unwrap()
    for t in body.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        if not t.get_text().strip():
            t.decompose()
    blocks = [c for c in body.children if getattr(c, 'name', None)]
    # title
    if n in TITLE_FROM_HEADING:
        first_h = next(b for b in blocks if b.name.startswith('h'))
        title = first_h.get_text().strip(); first_h.decompose(); notes.append('title = first heading')
    else:
        title = blocks[0].get_text().strip(); blocks[0].decompose()
    # heading levels: compress to h2..
    stack = []
    for h in body.find_all(re.compile('^h[1-6]$')):
        L = int(h.name[1])
        while stack and stack[-1][0] >= L:
            stack.pop()
        new = min(6, stack[-1][1] + 1) if stack else 2
        stack.append((L, new)); h.name = 'h%d' % new
    notes.append('outline normalised: first heading h2, no skipped levels')
    raw_text = ''.join(body.stripped_strings)
    # normalise text nodes
    for s in list(body.find_all(string=True)):
        new = norm(str(s), st)
        if new != str(s):
            s.replace_with(NavigableString(new))
    title = norm(title, dict(st))
    for a in body.find_all('a'):
        if a['href'].startswith('http'):
            a['rel'] = 'noopener'
    final_text = ''.join(body.stripped_strings)
    same = canon(final_text) == canon(raw_text)
    # internal links to glossary terms
    elig = [s for s in body.find_all(string=True)
            if s.find_parent(['a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']) is None and s.find_parent(['p', 'li'])]
    tnorm = canon(title)
    cands = []
    for tid, term, rx in TERMS:
        if canon(term) == tnorm or term in GENERIC:
            continue
        for idx, s in enumerate(elig):
            m = rx.search(str(s))
            if m:
                cands.append((len(term), -idx, tid, term, idx, m.start(), m.end())); break
    cands.sort(reverse=True)
    chosen, usedblk, used = [], set(), []
    for ln, ni, tid, term, idx, a, b in cands:
        blk = elig[idx].find_parent(['p', 'li'])
        if id(blk) in usedblk or len(chosen) >= 5:
            continue
        if any(i == idx and not (b <= a2 or a >= b2) for _, _, i, a2, b2 in used):
            continue
        chosen.append((tid, term, idx, a, b)); usedblk.add(id(blk)); used.append((tid, term, idx, a, b))
    by = {}
    for tid, term, idx, a, b in chosen:
        by.setdefault(idx, []).append((a, b, tid, term))
    for idx, items in by.items():
        s = elig[idx]; txt = str(s); pos = 0; frag = []
        for a, b, tid, term in sorted(items):
            frag.append(NavigableString(txt[pos:a]))
            link = soup.new_tag('a', href=quote('/فرهنگنامه/%s-%d' % (slug(term), tid), safe='/'))
            link.string = txt[a:b]; frag.append(link); pos = b
        frag.append(NavigableString(txt[pos:]))
        for f in reversed(frag):
            s.insert_after(f)
        s.extract()
    html = ''.join(str(c) for c in body.children).strip()
    html = re.sub(r'>\s+<', '><', html)
    plain = ' '.join(body.stripped_strings)
    words = len([w for w in TOK.findall(plain) if w.strip(ZW)])
    # excerpt
    paras = [re.sub(r'\s+', ' ', ''.join(x for x in p.strings if x.find_parent('sup') is None)).strip()
             for p in body.find_all('p') if p.find_parent('section') is None and p.find_parent('li') is None]
    paras = [p for p in paras if len(p) >= 60 and not p.startswith(('کلیدواژه', 'Keywords'))]
    ex = paras[0] if paras else ''
    if len(ex) < 120 and len(paras) > 1:
        ex = ex + ' ' + paras[1]
    if len(ex) > 160:
        cut = max((ex.rfind(c, 100, 160) for c in '.؟!'), default=-1)
        ex = ex[:cut + 1] if cut >= 100 else ex[:157].rsplit(' ', 1)[0] + '…'
    return dict(n=n, title=title, html=html, excerpt=ex, words=words, minutes=max(1, math.ceil(words / 200)),
                topic=TOPIC.get(n, 'روان‌شناسی تعاملی'), stats=st, same=same, links=[(t, tm) for t, tm, *_ in chosen], notes=notes,
                heads={'h%d' % k: len(body.find_all('h%d' % k)) for k in range(2, 7) if body.find_all('h%d' % k)},
                paras=len(body.find_all('p')), ext=len([a for a in body.find_all('a') if a['href'].startswith('http')]))


if __name__ == '__main__':
    os.makedirs(S + '/out', exist_ok=True)
    rows = []
    for n in range(1, N + 1):
        r = process(n); rows.append(r)
        json.dump(r, open('%s/out/a%02d.json' % (S, n), 'w', encoding='utf-8'), ensure_ascii=False)
        print('%02d | %s | w=%d min=%d | heads=%s p=%d ext=%d | links=%s | fixes=%s | text-unchanged=%s | excerpt=%d' % (
            n, r['title'][:42], r['words'], r['minutes'], r['heads'], r['paras'], r['ext'],
            [t for t, _ in r['links']], {k: v for k, v in r['stats'].items() if v}, r['same'], len(r['excerpt'])))
    with open(S + '/articles.csv', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['name', 'blog_id/.id', 'author_id/.id', 'content', 'eot_title', 'eot_excerpt', 'teaser_manual',
                    'eot_topic', 'eot_words', 'eot_minutes', 'eot_ltr', 'is_published'])
        for r in rows:
            w.writerow([r['title'], 46, 7, r['html'], r['title'], r['excerpt'], r['excerpt'], r['topic'],
                        r['words'], r['minutes'], 0, 0])
