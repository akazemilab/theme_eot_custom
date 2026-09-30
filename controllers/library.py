"""Public pages of the eot.ir library (website 1 only).

    /کتب                       books index (shelves)
    /کتب/<book>                one book: cover, facts, table of contents
    /کتب/<book>/<chapter>      one chapter
    /مقالات                    articles index
    /مقالات/<article>          one article
    /فرهنگنامه                 glossary index (alphabetical)
    /فرهنگنامه/<term>          one glossary term

<chapter>, <article> and <term> are "<slug>-<id>"; a wrong slug 301s to
the canonical one. The same records' stock /blog/... URLs 301 here too, so
each item has exactly one address. Any other website gets a 404.
"""
import re
from collections import OrderedDict
from urllib.parse import unquote

from urllib.parse import quote

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.http import request

from odoo.addons.website_blog.controllers.main import WebsiteBlog

from ..models.fa_text import fa_fold_letters, fa_match_key
from ..models.library import ALPHABET, ARTICLE_TOPICS, GLOSSARY_CATEGORIES, SHELVES, WEBSITE_ID
from . import seo_jsonld as ld

FA_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')

# The visible lead of /کتب (views/library.xml, lib_books) - also its meta description.
BOOKS_DESCRIPTION = ('آثار دکتر ناصرالدین کاظمی حقیقی در روان‌شناسی تعاملی، استعداد و تیزهوشی، خلاقیت، '
                     'و روان‌شناسی جامعه، سازمان و فرهنگ؛ هر کتاب با فهرست کامل فصل‌ها و متن آنلاین.')

# Shelf -> article topic used for "related articles" and back.
SHELF_TOPIC = {
    'gifted': 'تیزهوشی',
    'interactive': 'روان‌شناسی تعاملی',
    'creativity': 'خلاقیت',
    'society': 'جامعه، سازمان و فرهنگ',
}
TOPIC_SHELF = {
    'تیزهوشی': 'gifted', 'هوش و استعداد': 'gifted', 'آموزش و تحصیل': 'gifted',
    'خلاقیت': 'creativity', 'روان‌شناسی تعاملی': 'interactive',
    'بهداشت روان و درمان': 'interactive', 'جامعه، سازمان و فرهنگ': 'society',
}
# Too generic to be worth a "terms in this article" link.
TERM_STOPLIST = {'حمایت', 'نیاز', 'هیجان', 'هیجانی', 'تجربه', 'مفهوم', 'فرهنگ', 'ارزش', 'باور',
                 'اندیشه', 'پیشرفت', 'پیگیری', 'موفقیت', 'موفقیّت', 'ورزش', 'تاثیر', 'تامین', 'کنش',
                 'انتخاب', 'امنیت', 'توانایی', 'پیوند', 'تعهد', 'توفیق', 'پژوهش', 'تشخیص'}


def fa(value):
    return str(value).translate(FA_DIGITS)


def minutes_label(minutes):
    if minutes >= 90:
        hours = round(minutes / 60.0)
        return 'حدود %s ساعت' % fa(hours)
    return '%s دقیقه' % fa(minutes)


def length_level(minutes):
    return 1 if minutes <= 2 else 2 if minutes <= 5 else 3 if minutes <= 15 else 4 if minutes <= 30 else 5


def length_bucket(minutes):
    return 'short' if minutes <= 5 else 'medium' if minutes <= 15 else 'long'


def _is_library_site():
    return request.env.website and request.env.website.id == WEBSITE_ID


def _site_env(env):
    website = env.website
    return website and website.id == WEBSITE_ID


class EotLibrary(http.Controller):

    # ------------------------------------------------------------ helpers
    def _check(self):
        if not _is_library_site():
            raise NotFound()

    def _blogs(self, kind):
        return request.env['blog.blog'].sudo().with_context(lang='fa_IR').search(
            [('website_id', '=', WEBSITE_ID), ('eot_kind', '=', kind)],
            order='eot_order, id')

    def _posts(self, blogs, order='eot_sort, id'):
        return request.env['blog.post'].sudo().with_context(lang='fa_IR').search(
            [('blog_id', 'in', blogs.ids), ('is_published', '=', True)], order=order)

    def _item(self, blogs, slug):
        # Own parsing: Odoo's _unslug rejects slugs holding Persian marks
        # (tashdid, hamza above), which its own _slugify keeps.
        m = re.search(r'(?:^|-)(\d+)$', slug or '')
        if not m:
            raise NotFound()
        pid = int(m.group(1))
        post = request.env['blog.post'].sudo().with_context(lang='fa_IR').browse(pid).exists()
        if not post or post.blog_id not in blogs or not post.is_published:
            raise NotFound()
        return post

    def _canonical(self, record):
        """301 to the record's canonical URL when the requested one differs."""
        url = record.eot_url()
        path = request.httprequest.path
        if path.rstrip('/') != url:
            return request.redirect(url, code=301, local=True)
        return None

    def _book_card(self, blog, counts):
        count = counts.get(blog.id, 0)
        return {
            'name': blog.name,
            'url': blog.eot_url(),
            'shelf': blog.eot_shelf,
            'count': count,
            'count_label': 'اثر تک‌بخشی' if count == 1 else '%s فصل' % fa(count),
            'co': blog.eot_authors if blog.eot_authors and blog.eot_authors != 'دکتر ناصرالدین کاظمی حقیقی' else '',
            'size': 'eot-cover-s' if len(blog.name) > 34 else 'eot-cover-m' if len(blog.name) > 20 else '',
        }

    def _chapter_counts(self, books):
        if not books:
            return {}
        groups = request.env['blog.post'].sudo()._read_group(
            [('blog_id', 'in', books.ids), ('is_published', '=', True)], ['blog_id'], ['__count'])
        return {blog.id: count for blog, count in groups}

    def _article_row(self, post):
        m = post.eot_minutes or 1
        return {
            'name': post.eot_title or post.name,
            'url': post.eot_url(),
            'excerpt': post.eot_excerpt or '',
            'topic': post.eot_topic or '',
            'minutes': fa(m),
            'bucket': length_bucket(m),
            'ticks': [i < length_level(m) for i in range(5)],
            'ltr': post.eot_ltr,
        }

    def _toc(self, post):
        html = str(post.content or '')
        items = []
        for hid, label in re.findall(r'<h2[^>]*\bid="(s\d+)"[^>]*>(.*?)</h2>', html, flags=re.S):
            label = re.sub(r'<[^>]+>', '', label).strip()
            if label:
                items.append({'id': hid, 'label': label})
        return items

    def _render(self, template, values):
        values.setdefault('fa', fa)
        return request.render(template, values)

    # ------------------------------------------------------------ books
    @http.route(['/کتب'], type='http', auth='public', website=True, sitemap=True)
    def eot_books(self, **kw):
        self._check()
        books = self._blogs('book')
        counts = self._chapter_counts(books)
        shelves = []
        for key, (label, order) in sorted(SHELVES.items(), key=lambda kv: kv[1][1]):
            shelf_books = books.filtered(lambda b: b.eot_shelf == key and counts.get(b.id))
            if shelf_books:
                shelves.append({'key': key, 'label': label, 'num': fa(order),
                                'books': [self._book_card(b, counts) for b in shelf_books]})
        glossary = self._blogs('glossary')[:1]
        return self._render('theme_eot_custom.lib_books', {
            'shelves': shelves,
            'book_total': fa(sum(len(s['books']) for s in shelves)),
            'chapter_total': fa(sum(counts.values())),
            'shelf_total': fa(len(shelves)),
            'glossary': glossary,
            'glossary_count': fa(len(self._posts(glossary))) if glossary else '',
            'additional_title': 'کتاب‌ها',
            'eot_meta_description': BOOKS_DESCRIPTION,
            'structured_data': ld.render(
                ld.collection('کتاب‌ها', '/کتب', BOOKS_DESCRIPTION),
                ld.breadcrumb([('خانه', '/'), ('کتاب‌ها', '/کتب')])),
        })

    def _book_slug(self, slug):
        """The canonical slug for a typed/linked book slug. Books have no id
        in their URL, so match loosely: Arabic-keyboard letters, diacritics,
        half-space / space / hyphen differences all lead to the one book whose
        slug has the same fa_match_key. Unknown slugs are returned unchanged
        (and 404 in _book)."""
        key = fa_match_key(slug)
        books = request.env['blog.blog'].sudo().search(
            [('website_id', '=', WEBSITE_ID), ('eot_kind', '=', 'book')])
        hits = [b.eot_slug for b in books if b.eot_slug and fa_match_key(b.eot_slug) == key]
        if slug in hits or len(hits) != 1:
            return slug
        return hits[0]

    def _book(self, slug):
        book = request.env['blog.blog'].sudo().with_context(lang='fa_IR').search(
            [('website_id', '=', WEBSITE_ID), ('eot_kind', '=', 'book'), ('eot_slug', '=', slug)], limit=1)
        if not book:
            raise NotFound()
        return book

    @http.route(['/کتب/<string:book>'], type='http', auth='public', website=True,
                sitemap=lambda env, rule, qs: EotLibrary._sitemap_books(env, qs))
    def eot_book(self, book, **kw):
        self._check()
        slug = self._book_slug(book)
        if slug != book:
            return request.redirect(quote('/کتب/%s' % slug), code=301, local=True)
        book = self._book(book)
        chapters = self._posts(book, order='eot_number, id')
        if not chapters:
            raise NotFound()
        parts = OrderedDict()
        for ch in chapters:
            parts.setdefault(ch.eot_part or '', []).append(ch)
        has_parts = len(parts) > 1
        biggest = max(len(v) for v in parts.values())
        part_list = []
        for i, (name, chs) in enumerate(parts.items(), 1):
            minutes = sum(c.eot_minutes for c in chs)
            part_list.append({
                'num': fa(i), 'name': name, 'count': fa(len(chs)),
                'meta': '%s فصل · %s' % (fa(len(chs)), minutes_label(minutes)) if minutes else '%s فصل' % fa(len(chs)),
                'bar': '%d%%' % max(4, round(100.0 * len(chs) / biggest)),
                'chapters': [{'n': fa(c.eot_number or j), 'name': c.eot_title or c.name, 'url': c.eot_url()}
                             for j, c in enumerate(chs, 1)],
            })
        total = sum(c.eot_minutes for c in chapters)
        counts = self._chapter_counts(self._blogs('book'))
        same = self._blogs('book').filtered(lambda b: b.eot_shelf == book.eot_shelf and b != book and counts.get(b.id))
        topic = SHELF_TOPIC.get(book.eot_shelf)
        articles = self._posts(self._blogs('articles'), order='eot_words desc, id').filtered(
            lambda p: p.eot_topic == topic)[:2]
        return self._render('theme_eot_custom.lib_book', {
            'main_object': book,
            'book': book,
            'shelf_label': SHELVES.get(book.eot_shelf, ('',))[0],
            'card': self._book_card(book, counts),
            'single': len(chapters) == 1,
            'first': {'name': chapters[0].eot_title or chapters[0].name, 'url': chapters[0].eot_url()},
            'has_parts': has_parts,
            'parts': part_list,
            'chapter_count': fa(len(chapters)),
            'part_count': fa(len(parts)),
            'reading': minutes_label(total) if total else '',
            'same_shelf': [self._book_card(b, counts) for b in same[:4]],
            'related_articles': [self._article_row(a) for a in articles],
            'structured_data': ld.render(
                ld.book(book),
                ld.breadcrumb([('خانه', '/'), ('کتاب‌ها', '/کتب'), (book.name, book.eot_url())])),
        })

    @http.route(['/کتب/<string:book>/<string:chapter>'], type='http', auth='public', website=True,
                sitemap=lambda env, rule, qs: EotLibrary._sitemap_posts(env, 'book', qs))
    def eot_chapter(self, book, chapter, **kw):
        self._check()
        slug = self._book_slug(book)
        if slug != book:
            return request.redirect(quote('/کتب/%s/%s' % (slug, chapter)), code=301, local=True)
        book = self._book(book)
        post = self._item(book, chapter)
        redirect = self._canonical(post)
        if redirect:
            return redirect
        chapters = self._posts(book, order='eot_number, id')
        idx = list(chapters.ids).index(post.id)
        prev_ch = chapters[idx - 1] if idx > 0 else None
        next_ch = chapters[idx + 1] if idx + 1 < len(chapters) else None
        link = lambda c: c and {'name': c.eot_title or c.name, 'url': c.eot_url(), 'n': fa(c.eot_number or '')}
        title = post.eot_title or post.name
        full_title = '%s — %s' % (title, book.name)
        return self._render('theme_eot_custom.lib_chapter', {
            'main_object': post,
            # "<chapter> — <book> | هیجان اندیشه" stays under ~60 characters;
            # longer ones drop the book name (it is in the page and the markup).
            'additional_title': full_title if len(full_title) <= 45 else title,
            'structured_data': ld.render(
                ld.chapter(post, book),
                ld.breadcrumb([('خانه', '/'), ('کتاب‌ها', '/کتب'), (book.name, book.eot_url()),
                               (title, post.eot_url())])),
            'post': post,
            'book': book,
            'card': self._book_card(book, {book.id: len(chapters)}),
            'position': '%s از %s' % (fa(idx + 1), fa(len(chapters))),
            'progress': '%d%%' % round(100.0 * (idx + 1) / len(chapters)),
            'prev': link(prev_ch),
            'next': link(next_ch),
            'toc': self._toc(post),
            'minutes': minutes_label(post.eot_minutes or 1),
            'chapters': [dict(link(c), current=(c == post)) for c in chapters],
        })

    # ------------------------------------------------------------ articles
    @http.route(['/مقالات'], type='http', auth='public', website=True, sitemap=True)
    def eot_articles(self, **kw):
        self._check()
        blog = self._blogs('articles')[:1]
        if not blog:
            raise NotFound()
        posts = self._posts(blog)
        rows = [self._article_row(p) for p in posts]
        topics = [{'name': t, 'count': fa(sum(1 for r in rows if r['topic'] == t))}
                  for t in ARTICLE_TOPICS if any(r['topic'] == t for r in rows)]
        buckets = {b: fa(sum(1 for r in rows if r['bucket'] == b)) for b in ('short', 'medium', 'long')}
        longest = posts.sorted(lambda p: -p.eot_words)[:3]
        return self._render('theme_eot_custom.lib_articles', {
            'main_object': blog,
            'blog': blog,
            'structured_data': ld.render(
                ld.collection(blog.name, '/مقالات', blog.eot_description),
                ld.breadcrumb([('خانه', '/'), ('مقالات', '/مقالات')])),
            'rows': rows,
            'total': fa(len(rows)),
            'topics': topics,
            'buckets': buckets,
            'featured': [self._article_row(p) for p in longest],
        })

    def _glossary_terms_in(self, text):
        glossary = self._blogs('glossary')
        if not glossary:
            return []
        terms = self._posts(glossary)
        plain = re.sub(r'<[^>]+>', ' ', text or '').replace('‌', ' ')
        found = []
        for t in terms:
            name = (t.eot_title or t.name or '').strip()
            if len(name) < 4 or name in TERM_STOPLIST:
                continue
            hits = plain.count(name.replace('‌', ' '))
            if hits:
                found.append((hits * (2 if ' ' in name else 1), t))
        found.sort(key=lambda x: (-x[0], x[1].eot_sort or ''))
        return [{'name': t.eot_title or t.name, 'url': t.eot_url(), 'english': (t.eot_english or '').split('؛')[0].strip()}
                for _s, t in found[:3]]

    @http.route(['/مقالات/<string:article>'], type='http', auth='public', website=True,
                sitemap=lambda env, rule, qs: EotLibrary._sitemap_posts(env, 'articles', qs))
    def eot_article(self, article, **kw):
        self._check()
        blog = self._blogs('articles')[:1]
        post = self._item(blog, article)
        redirect = self._canonical(post)
        if redirect:
            return redirect
        same = self._posts(blog, order='eot_words desc, id').filtered(
            lambda p: p.eot_topic == post.eot_topic and p != post)[:3]
        shelf = TOPIC_SHELF.get(post.eot_topic)
        books = self._blogs('book').filtered(lambda b: b.eot_shelf == shelf)[:1]
        counts = self._chapter_counts(books)
        m = post.eot_minutes or 1
        toc = self._toc(post)
        crumbs = [('خانه', '/'), ('مقالات', '/مقالات'), (post.eot_title or post.name, post.eot_url())]
        return self._render('theme_eot_custom.lib_article', {
            'main_object': post,
            'post': post,
            'structured_data': ld.render(ld.article(post), ld.breadcrumb(crumbs)),
            'row': self._article_row(post),
            'reading': minutes_label(m),
            'length_label': {'short': 'مقاله کوتاه', 'medium': 'مقاله متوسط', 'long': 'مقاله بلند'}[length_bucket(m)],
            'toc': toc if 3 <= len(toc) <= 24 and m > 5 else [],
            'terms': self._glossary_terms_in(str(post.content or '')),
            'related': [self._article_row(p) for p in same],
            'book': self._book_card(books, counts) if books and counts.get(books.id) else None,
        })

    # ------------------------------------------------------------ glossary
    @http.route(['/فرهنگنامه', '/فرهنگنامه/روانشناسی-تعاملی'], type='http', auth='public',
                website=True, sitemap=lambda env, rule, qs: EotLibrary._sitemap_static(env, '/فرهنگنامه', qs))
    def eot_glossary(self, **kw):
        self._check()
        if request.httprequest.path.rstrip('/') != '/فرهنگنامه':
            return request.redirect('/فرهنگنامه', code=301, local=True)
        blog = self._blogs('glossary')[:1]
        if not blog:
            raise NotFound()
        terms = self._posts(blog)
        groups = OrderedDict((c, []) for c in ALPHABET)
        for t in terms:
            letter = t.eot_letter if t.eot_letter in groups else ALPHABET[0]
            groups[letter].append({'name': t.eot_title or t.name, 'url': t.eot_url(),
                                   'english': (t.eot_english or '').split('؛')[0].strip(),
                                   'topic': t.eot_topic or ''})
        letters = [{'c': c, 'count': fa(len(v)), 'on': bool(v), 'anchor': 'l-%d' % i}
                   for i, (c, v) in enumerate(groups.items())]
        cats = [{'name': c, 'count': fa(sum(1 for t in terms if t.eot_topic == c))}
                for c in GLOSSARY_CATEGORIES]
        return self._render('theme_eot_custom.lib_glossary', {
            'main_object': blog,
            'blog': blog,
            'structured_data': ld.render(
                ld.term_set(blog),
                ld.breadcrumb([('خانه', '/'), ('فرهنگنامه', '/فرهنگنامه')])),
            'total': fa(len(terms)),
            'letters': letters,
            'groups': [{'c': l['c'], 'anchor': l['anchor'], 'count': l['count'], 'items': groups[l['c']]}
                       for l in letters if l['on']],
            'cats': [c for c in cats if c['count'] != fa(0)],
        })

    @http.route(['/فرهنگنامه/<string:term>'], type='http', auth='public', website=True,
                sitemap=lambda env, rule, qs: EotLibrary._sitemap_posts(env, 'glossary', qs))
    def eot_term(self, term, **kw):
        self._check()
        blog = self._blogs('glossary')[:1]
        post = self._item(blog, term)
        redirect = self._canonical(post)
        if redirect:
            return redirect
        terms = self._posts(blog)
        ids = list(terms.ids)
        idx = ids.index(post.id)
        prev_t = terms[idx - 1] if idx > 0 else None
        next_t = terms[idx + 1] if idx + 1 < len(terms) else None
        linked_ids = [int(i) for i in re.findall(r'href="/فرهنگنامه/[^"]*?-(\d+)"', unquote(str(post.content or '')))]
        linked = request.env['blog.post'].sudo().with_context(lang='fa_IR').browse(
            list(OrderedDict.fromkeys(i for i in linked_ids if i != post.id))).exists().filtered(
            lambda p: p.is_published and p.blog_id == blog)
        same = terms.filtered(lambda p: p.eot_topic and p.eot_topic == post.eot_topic and p != post and p not in linked)
        # neighbours in the same category, around this term alphabetically
        same_list = list(same)
        pos = next((i for i, p in enumerate(same_list) if (p.eot_sort or '') > (post.eot_sort or '')), len(same_list))
        near = same_list[max(0, pos - 2):pos + 2][:4]
        item = lambda p: {'name': p.eot_title or p.name, 'url': p.eot_url(),
                          'english': (p.eot_english or '').split('؛')[0].strip()}
        letter_index = [c for c in ALPHABET].index(post.eot_letter) if post.eot_letter in ALPHABET else 0
        letters = []
        present = set(terms.mapped('eot_letter'))
        for i, c in enumerate(ALPHABET):
            letters.append({'c': c, 'on': c in present, 'anchor': 'l-%d' % i, 'current': c == post.eot_letter})
        english = [e.strip() for e in (post.eot_english or '').split('؛') if e.strip()]
        return self._render('theme_eot_custom.lib_term', {
            'main_object': post,
            'post': post,
            'blog': blog,
            'english': english,
            'structured_data': ld.render(
                ld.term_set(blog), ld.term(post, english),
                ld.breadcrumb([('خانه', '/'), ('فرهنگنامه', '/فرهنگنامه'),
                               (post.eot_title or post.name, post.eot_url())])),
            'reading': minutes_label(post.eot_minutes or 1),
            'prev': prev_t and item(prev_t),
            'next': next_t and item(next_t),
            'linked': [item(p) for p in linked[:6]],
            'same': [item(p) for p in near],
            'letters': letters,
            'letter_anchor': 'l-%d' % letter_index,
            'letter_count': fa(len(terms.filtered(lambda p: p.eot_letter == post.eot_letter))),
        })

    # ------------------------------------------------------------ sitemap
    @staticmethod
    def _sitemap_static(env, loc, qs):
        if _site_env(env) and (not qs or qs.lower() in loc.lower()):
            yield {'loc': loc}

    @staticmethod
    def _sitemap_books(env, qs):
        if not _site_env(env):
            return
        for blog in env['blog.blog'].sudo().search([('website_id', '=', WEBSITE_ID), ('eot_kind', '=', 'book')]):
            loc = blog.eot_url()
            if not qs or qs.lower() in loc.lower():
                yield {'loc': loc}

    @staticmethod
    def _sitemap_posts(env, kind, qs):
        if not _site_env(env):
            return
        blogs = env['blog.blog'].sudo().search([('website_id', '=', WEBSITE_ID), ('eot_kind', '=', kind)])
        posts = env['blog.post'].sudo().with_context(lang='fa_IR').search(
            [('blog_id', 'in', blogs.ids), ('is_published', '=', True)])
        for post in posts:
            loc = post.eot_url()
            if not qs or qs.lower() in loc.lower():
                yield {'loc': loc, 'lastmod': (post.write_date or post.create_date).date()}


def _library_blog_prefixes(env):
    blogs = env['blog.blog'].sudo().search([('website_id', '=', WEBSITE_ID), ('eot_kind', '!=', False)])
    return tuple('/blog/%s' % env['ir.http']._slug(b) for b in blogs)


def _sitemap_blog_post_filtered(env, rule, qs):
    skip = _library_blog_prefixes(env) if _site_env(env) else ()
    for rec in WebsiteBlog.sitemap_blog_post(env, rule, qs):
        if not (skip and rec.get('loc', '').startswith(skip)):
            yield rec


def _sitemap_blog_filtered(env, rule, qs):
    # Website 1: /blog and every blog listing redirect to the library pages.
    if _site_env(env):
        return
    yield from WebsiteBlog.sitemap_blog(env, rule, qs)


def _sitemap_blog_feed_filtered(env, rule, qs):
    # Website 1: feeds are disallowed in robots.txt, so keep them out of the
    # sitemap (they were 23 of its URLs). Other websites keep their feeds.
    if _site_env(env):
        return
    for blog in env['blog.blog'].search(env.website.website_domain()):
        loc = '/blog/%s/feed' % env['ir.http']._slug(blog)
        if not qs or qs.lower() in loc.lower():
            yield {'loc': loc}


def _url_segment_key(index):
    """Match key of the /blog/... URL segment at `index`, without its trailing id."""
    parts = [p for p in unquote(request.httprequest.path).split('/') if p]
    if len(parts) <= index:
        return ''
    return fa_match_key(re.sub(r'-\d+$', '', parts[index]))


class EotWebsiteBlog(WebsiteBlog):
    """Library blogs keep one address each: their stock /blog URLs 301 to
    the library pages (website 1 only; other websites are unaffected).

    Old-site URLs reuse record ids that now belong to different books and
    posts (e.g. /blog/خلاقیت-31 is the id of another book today). So on
    website 1 the name in the URL must match the record; otherwise the
    library item with that name is used, and if there is none: 404, never
    somebody else's page."""

    def _eot_blog_by_key(self, key):
        blogs = request.env['blog.blog'].sudo().with_context(lang='fa_IR').search(
            [('website_id', '=', WEBSITE_ID), ('eot_kind', '!=', False)])
        return blogs.filtered(lambda b: fa_match_key(b.name) == key)[:1]

    def _eot_post_by_key(self, key, prefer_blog=None):
        blogs = request.env['blog.blog'].sudo().search(
            [('website_id', '=', WEBSITE_ID), ('eot_kind', '!=', False)])
        posts = request.env['blog.post'].sudo().with_context(lang='fa_IR').search(
            [('blog_id', 'in', blogs.ids), ('is_published', '=', True)])
        found = posts.filtered(lambda p: key in (fa_match_key(p.eot_title or ''), fa_match_key(p.name)))
        if prefer_blog and len(found) > 1:
            found = found.filtered(lambda p: p.blog_id == prefer_blog) or found
        return found.sorted('id')[:1]

    @http.route(sitemap=_sitemap_blog_post_filtered)
    def blog_post(self, blog, blog_post, tag_id=None, page=1, enable_editor=None, **post):
        if _is_library_site() and not enable_editor:
            target = blog_post.sudo().with_context(lang='fa_IR').exists()
            key = _url_segment_key(2)
            if target and target.blog_id.eot_kind and key and key not in (
                    fa_match_key(target.eot_title or ''), fa_match_key(target.name)):
                target = self._eot_post_by_key(key)
                if not target:
                    raise NotFound()
            if target and target.blog_id.eot_kind and target.is_published:
                return request.redirect(target.eot_url(), code=301, local=True)
        return super().blog_post(blog, blog_post, tag_id=tag_id, page=page, enable_editor=enable_editor, **post)

    @http.route(sitemap=_sitemap_blog_filtered)
    def blog(self, blog=None, tag=None, page=1, search=None, **opt):
        if _is_library_site():
            if blog:
                target = blog.sudo().with_context(lang='fa_IR').exists()
                key = _url_segment_key(1)
                if target and key and key != fa_match_key(target.name):
                    target = self._eot_blog_by_key(key)
                    if not target:
                        raise NotFound()
                if target and target.eot_kind:
                    return request.redirect(target.eot_url(), code=301, local=True)
            if not blog and not tag and not search:
                return request.redirect('/مقالات', code=302, local=True)
        return super().blog(blog=blog, tag=tag, page=page, search=search, **opt)

    @http.route(sitemap=_sitemap_blog_feed_filtered)
    def blog_feed(self, blog, limit='15', **kwargs):
        return super().blog_feed(blog, limit=limit, **kwargs)
