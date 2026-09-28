"""Library data for eot.ir: books, articles and the glossary (website 1).

The content was carried over from the old instance as blog.blog / blog.post
records (one blog per book, the "مقالات" blog, the glossary blog). The old
pages had their own layout baked into each post's HTML (breadcrumbs, meta
boxes, "in this page" boxes, JSON-LD pointing at sepehrtherapy.ir, chapter
navigation). The new page templates render all of that themselves, so the
post HTML is normalised once into plain content, and the fields every page
type needs (shelf, topic, English equivalent, reading time, ...) are stored
on the records.

``BlogBlog._eot_library_sync`` does that. It runs on every module upgrade
(data/library_sync.xml) but only does work when LIBRARY_VERSION is higher
than the version it last applied, so edits made in the backend afterwards
survive later upgrades until the normaliser itself changes. The original
HTML of every post is kept in table ``eot_library_backup`` (written once,
never overwritten); the normaliser always starts from that copy.

Scope: only blogs of website 1 whose name is listed below. Website 3 is
never read or written.
"""
import logging
import math
import re
from urllib.parse import unquote

from lxml import html as lxml_html

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

WEBSITE_ID = 1
LIBRARY_VERSION = 2
PARAM_VERSION = 'theme_eot_custom.library_version'
PARAM_PUBLISHED = 'theme_eot_custom.library_published'

ARTICLES_BLOG = 'مقالات'
GLOSSARY_BLOG = 'فرهنگنامه روان‌شناسی تعاملی'
DEFAULT_AUTHOR = 'دکتر ناصرالدین کاظمی حقیقی'

# key: (label, order)
SHELVES = {
    'gifted': ('استعداد و تیزهوشی', 1),
    'interactive': ('روان‌شناسی تعاملی', 2),
    'creativity': ('خلاقیت', 3),
    'society': ('جامعه، سازمان و فرهنگ', 4),
}

# blog name -> (url slug, shelf, order in shelf, description)
BOOKS = {
    'استعداد و تیزهوشی': ('استعداد-و-تیزهوشی', 'gifted', 1,
        'مجموعه‌ای گسترده درباره روان‌شناسی استعداد و تیزهوشی؛ شامل ویژگی‌های شناختی، انگیزشی، شخصیتی، خانوادگی، اجتماعی و آموزشی افراد تیزهوش.'),
    'روان‌شناسی کودکان تیزهوش و روش‌های آموزش ویژه': ('روان-شناسی-کودکان-تیزهوش-و-روش-های-اموزش-ویژه', 'gifted', 2,
        'کتابی درباره ویژگی‌های کودکان تیزهوش، شناسایی و مشاوره، هوش و خلاقیت، و روش‌های آموزش ویژه مانند غنی‌سازی و تسریع تحصیلی.'),
    'آموزش و پرورش برای استعداد و تیزهوشی': ('اموزش-و-پرورش-برای-استعداد-و-تیزهوشی', 'gifted', 3,
        'کتابی درباره آموزش و پرورش استعداد و تیزهوشی؛ شامل روان‌شناسی تعاملی، سیاست‌های آموزشی، غنی‌سازی، تلفیق، تفکیک و تسریع تحصیلی.'),
    'استعداد ریاضی': ('استعداد-ریاضی', 'gifted', 4,
        'کتابی درباره استعداد و تیزهوشی ریاضی؛ شامل ویژگی‌های نگرشی و شخصیتی، شناسایی استعداد، آمادگی ریاضی و تسریع تحصیلی.'),
    'خانواده و رضایت محیطی نوجوانان تیزهوش': ('خانواده-و-رضایت-محیطی-نوجوانان-تیزهوش', 'gifted', 5,
        'بررسی نقش خانواده، فرهنگ و انتظارات اجتماعی در رضایت محیطی نوجوانان تیزهوش و چگونگی شکل‌گیری استقلال و سازگاری آنان.'),
    'پرورش استعداد': ('پرورش-استعداد', 'gifted', 6,
        'متنی درباره ارکان نظام ویژه پرورش استعداد؛ از تفرّد و مرجعیت تا همگنی انعطافی، فضای غنی‌ساخته، آموزش خاص و ارتقای زمینه‌ای.'),
    'هیجان اندیشه': ('هیجان-اندیشه', 'interactive', 1,
        'اثری درباره نظریه هیجان اندیشه و تعامل شناخت، عاطفه، انگیزش و شخصیت؛ با بحث‌هایی درباره تحول، هویت‌یابی، تیزهوشی و پویایی روانی.'),
    'زمینهٔ روان‌شناسی تعاملی': ('زمینه-روانشناسی-تعاملی', 'interactive', 2,
        'معرفی مبانی، تاریخچه و اصول روان‌شناسی تعاملی؛ از نظام‌یافتگی و روش تحقیق تا تشخیص، تیزهوشی، شخصیت و کاربردهای این رویکرد.'),
    'روان‌شناسی انتظار': ('روانشناسی-انتظار', 'interactive', 3,
        'بررسی مفهوم انتظار در روان‌شناسی و روان‌درمانی تعاملی و ارتباط آن با پیشرفت، آرامش، رضایت از زندگی، معنویت و شخصیت.'),
    'خودشناسی': ('خودشناسی', 'interactive', 4,
        'متنی درباره مؤلفه‌های خودشناسی و ویژگی‌های روانی فرد، از پیوندجویی و ارزش‌گذاری تا پایداری، انعطاف روانی، استقلال و هیجان‌پذیری.'),
    'درآمدی بر روان‌درمانی تعاملی': ('درامدی-بر-روان-درمانی-تعاملی', 'interactive', 5,
        'درآمدی بر روان‌درمانی تعاملی با تمرکز بر تعادل روان، درمان در چشم‌انداز تعاملی، معنویت، ارزش‌ها، بهزیستی معنوی و معنایابی.'),
    'پایایی روانی': ('پایایی-روانی', 'interactive', 6,
        'متنی متمرکز بر مفهوم پایایی روانی و جایگاه آن در فهم پایداری، سازگاری و استمرار عملکرد روانی فرد.'),
    'چشم‌انداز تعاملی هوش موفق': ('چشم-انداز-تعاملی-هوش-موفق', 'interactive', 7,
        'متنی درباره مفهوم هوش موفق از چشم‌انداز روان‌شناسی تعاملی و نحوه نگاه تعاملی به توانایی، عملکرد و موفقیت.'),
    'خلّاقیّت': ('خلاقیت', 'creativity', 1,
        'کتابی درباره روان‌شناسی خلاقیت؛ از رویکردهای نظری و جایگاه خلاقیت در روان‌شناسی تعاملی تا رابطه خلاقیت با هوش، تیزهوشی و شخصیت.'),
    'خلّاقیّت، هوش و تیزهوشی': ('خلاقیت-هوش-و-تیزهوشی', 'creativity', 2,
        'متنی درباره رابطه خلاقیت با هوش و تیزهوشی و ویژگی‌های اندیشه و شخصیت افراد خلاق.'),
    'نخبه‌شناسی': ('نخبه-شناسی', 'society', 1,
        'کتابی با چشم‌انداز روان‌شناختی و جامعه‌شناختی درباره مبانی نخبگی، نظریه‌های نخبگان، فرهنگ و نخبگی، نخبگی فرهنگی و مشارکت نخبگان.'),
    'روان‌شناسی کار و مدیریت': ('روانشناسی-کار-و-مدیریت', 'society', 2,
        'بررسی روان‌شناسی کار و مدیریت با موضوعاتی مانند رضایت شغلی، تعهد سازمانی، فضای سازمانی، امنیت شغلی، حمایت محیطی و مدیریت.'),
    'روان‌شناسی سازمانی': ('روانشناسی-سازمانی', 'society', 3,
        'بررسی روان‌شناختی سازمان و محیط کار با تمرکز بر رضایت شغلی، تعهد سازمانی، فضای سازمانی، امنیت شغلی، حمایت محیطی و عدالت حرفه‌ای.'),
    'روان‌شناسی فرهنگی': ('روانشناسی-فرهنگی', 'society', 4,
        'بررسی پیوند فرهنگ و فرایندهای روانی با موضوعاتی مانند معنویت، ارزش‌ها، آرامش روان، تیزهوشی، خلاقیت و نقش فرهنگ در شکل‌گیری رفتار.'),
    'بررسی مبانی نظری نخبگی': ('مبانی-نظری-نخبگی', 'society', 5,
        'پژوهشی درباره مبانی نظری نخبگی و انواع آن برحسب منبع و حیطه، همراه با بحث‌هایی درباره هوش، تیزهوشی، خلاقیت و نتایج پژوهشی.'),
}

GLOSSARY_CATEGORIES = [
    'مبانی روان‌شناسی تعاملی', 'ظرفیت‌های روانی', 'هویت و خود',
    'خشنودی و بهداشت', 'پرورش و درمان', 'جامعه و سازمان',
]

ARTICLE_TOPICS = [
    'تیزهوشی', 'هوش و استعداد', 'خلاقیت', 'روان‌شناسی تعاملی',
    'بهداشت روان و درمان', 'آموزش و تحصیل', 'جامعه، سازمان و فرهنگ',
]
# First matching rule wins (matched against the title with ZWNJ removed).
ARTICLE_TOPIC_RULES = [
    ('خلاقیت', ['خلاق', 'خلّاق', 'آفرین', 'creativ', 'Creativ']),
    ('جامعه، سازمان و فرهنگ', ['نخبگ', 'نخبه']),
    ('تیزهوشی', ['تیزهوش', 'استثنایی', 'دودامنه']),
    ('هوش و استعداد', ['هوش', 'استعداد']),
    ('روان‌شناسی تعاملی', ['تعاملی', 'هیجان اندیشه', 'انگاره', 'خردورزی', 'دادپویی',
                           'خودپویشی', 'ناپایایی', 'شخصیت', 'هیجان', 'نیروی روانی']),
    ('بهداشت روان و درمان', ['بهداشت', 'درمان', 'مشاوره', 'پایایی', 'پایداری', 'بیتابی',
                             'استواری', 'آرامش', 'رضایت', 'معنا', 'پاکزیستی', 'سرسختی']),
    ('آموزش و تحصیل', ['تحصیل', 'آموزش', 'یادگیری', 'خودباوری', 'غنی']),
    ('جامعه، سازمان و فرهنگ', ['فرهنگ', 'سازمان', 'جامعه', 'انتظار', 'مکاتب', 'علم', 'شغل', 'مدیریت']),
]

# Persian alphabetical order ("آ" is its own group, first).
ALPHABET = 'آ ا ب پ ت ث ج چ ح خ د ذ ر ز ژ س ش ص ض ط ظ ع غ ف ق ک گ ل م ن و ه ی'.split()
_CHAR_NORMAL = {'ي': 'ی', 'ى': 'ی', 'ك': 'ک', 'ة': 'ه', 'أ': 'ا', 'إ': 'ا', 'ؤ': 'و', 'ئ': 'ی', 'ۀ': 'ه'}
_ORDER = {c: i for i, c in enumerate(ALPHABET)}
_WS = re.compile(r'\s+')
_WORD_RE = re.compile(r'\S+')


def fa_normalize(text):
    return ''.join(_CHAR_NORMAL.get(c, c) for c in (text or ''))


def fa_sort_key(text):
    """Sort key following the Persian alphabet (space sorts first)."""
    out = []
    for c in fa_normalize(text):
        if c == ' ':
            out.append('!')
        elif c in _ORDER:
            out.append(chr(0x41 + _ORDER[c]))
        elif c.isdigit() or ('a' <= c.lower() <= 'z'):
            out.append('~' + c.lower())
        # ZWNJ, tashdid, hamza above and punctuation are ignored
    return ''.join(out)


def fa_letter(text):
    for c in fa_normalize(text):
        if c in _ORDER:
            return c
    return ''


def _text(el):
    return _WS.sub(' ', el.text_content() if el is not None else '').strip()


def _truncate_words(text, n):
    words = text.split()
    if len(words) <= n:
        return text
    return ' '.join(words[:n]).rstrip('،,؛:') + '…'


class BlogBlog(models.Model):
    _inherit = 'blog.blog'

    eot_kind = fields.Selection(
        [('book', 'Book'), ('articles', 'Articles'), ('glossary', 'Glossary')],
        string='EOT library type', index=True, copy=False)
    eot_slug = fields.Char('EOT URL slug', copy=False)
    eot_shelf = fields.Selection([(k, v[0]) for k, v in SHELVES.items()], string='EOT shelf')
    eot_order = fields.Integer('EOT order in shelf')
    eot_subtitle = fields.Char('EOT subtitle')
    eot_authors = fields.Char('EOT authors')
    eot_description = fields.Text('EOT description')

    def eot_url(self):
        self.ensure_one()
        if self.eot_kind == 'book':
            return '/کتب/%s' % self.eot_slug
        if self.eot_kind == 'articles':
            return '/مقالات'
        if self.eot_kind == 'glossary':
            return '/فرهنگنامه'
        return '/blog/%s' % self.env['ir.http']._slug(self)

    @api.model
    def _eot_library_blogs(self):
        names = list(BOOKS) + [ARTICLES_BLOG, GLOSSARY_BLOG]
        blogs = self.with_context(lang='fa_IR', active_test=False).search(
            [('website_id', '=', WEBSITE_ID)])
        return blogs.filtered(lambda b: b.name in names)

    # ------------------------------------------------------------------
    # Sync (called from data/library_sync.xml on every upgrade)
    # ------------------------------------------------------------------
    @api.model
    def _eot_library_sync(self):
        self = self.with_context(tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
        ICP = self.env['ir.config_parameter'].sudo()
        done = ICP.get_int(PARAM_VERSION, 0)
        blogs = self._eot_library_blogs()
        if not blogs:
            _logger.info('eot library: no library blogs on website %s, nothing to do', WEBSITE_ID)
            return True
        if done < LIBRARY_VERSION:
            self._eot_sync_blogs(blogs)
            self.env['blog.post']._eot_sync_posts(blogs)
            ICP.set_int(PARAM_VERSION, LIBRARY_VERSION)
            _logger.info('eot library: normalised to version %s', LIBRARY_VERSION)
        if not ICP.get_bool(PARAM_PUBLISHED):
            self._eot_publish(blogs)
            ICP.set_bool(PARAM_PUBLISHED, True)
            _logger.info('eot library: published and added to the menu')
        return True

    @api.model
    def _eot_sync_blogs(self, blogs):
        for blog in blogs.with_context(lang='fa_IR'):
            vals = {}
            if blog.name == ARTICLES_BLOG:
                vals = {'eot_kind': 'articles', 'eot_description': blog.subtitle or False}
            elif blog.name == GLOSSARY_BLOG:
                vals = {'eot_kind': 'glossary', 'eot_description': blog.subtitle or False}
            else:
                slug, shelf, order, desc = BOOKS[blog.name]
                sub = (blog.subtitle or '').strip()
                # The old subtitle holds either the author line or a real subtitle.
                if 'کاظمی' in sub:
                    authors, subtitle = sub, False
                else:
                    authors, subtitle = DEFAULT_AUTHOR, sub or False
                vals = {'eot_kind': 'book', 'eot_slug': slug, 'eot_shelf': shelf,
                        'eot_order': order, 'eot_description': desc,
                        'eot_authors': authors, 'eot_subtitle': subtitle}
            # Odoo's URL matcher rejects slugs holding Persian marks (tashdid,
            # hamza above); give such blogs a clean seo_name so their stock
            # /blog/... URLs (and feeds) resolve.
            if re.search(r'[\u064b-\u065f\u0670\u0654]', blog.name or ''):
                clean = re.sub(r'[\u064b-\u065f\u0670\u0654]', '', blog.name)
                vals['seo_name'] = self.env['ir.http']._slugify(clean.replace('ۀ', 'ه'))
            blog.write(vals)

    @api.model
    def _eot_publish(self, blogs):
        Post = self.env['blog.post'].with_context(active_test=False)
        posts = Post.search([('blog_id', 'in', blogs.ids)])
        keep = posts.filtered(lambda p: p.eot_words > 0)
        # Duplicate article titles: publish only the longest copy.
        groups = {}
        for p in keep.filtered(lambda p: p.blog_id.eot_kind == 'articles'):
            key = fa_sort_key(p.with_context(lang='fa_IR').name)
            groups.setdefault(key, []).append(p)
        for dupes in groups.values():
            if len(dupes) > 1:
                dupes.sort(key=lambda p: p.eot_words, reverse=True)
                for extra in dupes[1:]:
                    keep -= extra
        keep.write({'is_published': True})
        (posts - keep).write({'is_published': False})

        # Header menu: replace the stock "بلاگ" (/blog) entry with the library.
        # manual_url (not url): writing url would link the menu to the old,
        # unpublished website.page at the same address and hide the entry.
        Menu = self.env['website.menu']
        top = self.env['website'].browse(WEBSITE_ID).menu_id
        if not top:
            return
        wanted = [('کتاب‌ها', '/کتب', 20), ('مقالات', '/مقالات', 21), ('فرهنگنامه', '/فرهنگنامه', 22)]
        blog_menu = top.child_id.filtered(lambda m: m.url == '/blog')
        existing = {m.url for m in top.child_id}
        for i, (name, url, seq) in enumerate(wanted):
            if url in existing:
                continue
            if i == 0 and blog_menu:
                blog_menu[:1].write({'manual_url': url, 'page_id': False, 'sequence': seq})
                for lang in ('en_US', 'fa_IR'):
                    blog_menu[:1].with_context(lang=lang).write({'name': name})
            else:
                Menu.create({'name': name, 'manual_url': url, 'parent_id': top.id,
                             'website_id': WEBSITE_ID, 'sequence': seq})


class BlogPost(models.Model):
    _inherit = 'blog.post'

    eot_title = fields.Char('EOT title', help='Title without the chapter number prefix')
    eot_number = fields.Integer('EOT chapter number')
    eot_part = fields.Char('EOT book part')
    eot_topic = fields.Char('EOT topic / category', index=True)
    eot_subtopic = fields.Char('EOT subcategory')
    eot_english = fields.Char('EOT English equivalent')
    eot_excerpt = fields.Text('EOT excerpt')
    eot_words = fields.Integer('EOT word count')
    eot_minutes = fields.Integer('EOT reading minutes')
    eot_letter = fields.Char('EOT first letter', index=True)
    eot_sort = fields.Char('EOT sort key', index=True)
    eot_ltr = fields.Boolean('EOT left-to-right text')

    def eot_url(self):
        self.ensure_one()
        blog = self.blog_id
        slug = self.env['ir.http']._slug((self.id, self.eot_title or self.name))
        if blog.eot_kind == 'glossary':
            return '/فرهنگنامه/%s' % slug
        if blog.eot_kind == 'articles':
            return '/مقالات/%s' % slug
        if blog.eot_kind == 'book':
            return '/کتب/%s/%s' % (blog.eot_slug, slug)
        return '/blog/%s/%s' % (self.env['ir.http']._slug(blog), self.env['ir.http']._slug(self))

    # ------------------------------------------------------------------
    @api.model
    def _eot_sync_posts(self, blogs):
        cr = self.env.cr
        cr.execute("""
            CREATE TABLE IF NOT EXISTS eot_library_backup (
                post_id integer PRIMARY KEY,
                content jsonb,
                backed_up timestamp DEFAULT (now() at time zone 'utc')
            )""")
        posts = self.with_context(lang='fa_IR', active_test=False).search(
            [('blog_id', 'in', blogs.ids)])
        cr.execute("""
            INSERT INTO eot_library_backup (post_id, content)
            SELECT id, content FROM blog_post WHERE id = ANY(%s)
            ON CONFLICT (post_id) DO NOTHING""", [posts.ids])
        cr.execute("SELECT post_id, content FROM eot_library_backup WHERE post_id = ANY(%s)", [posts.ids])
        raw = {}
        for pid, content in cr.fetchall():
            content = content or {}
            raw[pid] = content.get('fa_IR') or content.get('en_US') or ''

        # Pass 1: titles, numbers, parts, and the map old-site id -> post.
        old_ids = {}
        for post in posts:
            kind = post.blog_id.eot_kind
            name = (post.name or '').strip()
            vals = {'eot_title': name, 'eot_number': 0, 'eot_part': False,
                    'eot_ltr': not re.search(r'[؀-ۿ]', name)}
            if kind == 'book':
                m = re.match(r'^\s*(\d+)\s*[.\-]\s*(.+)$', name)
                if m:
                    vals['eot_number'] = int(m.group(1))
                    vals['eot_title'] = m.group(2).strip()
                sub = (post.subtitle or '').strip()
                if ' — ' in sub:
                    vals['eot_part'] = sub.split(' — ', 1)[1].strip()
            vals['eot_sort'] = fa_sort_key(vals['eot_title'])
            vals['eot_letter'] = fa_letter(vals['eot_title'])
            post.write(vals)
            m = re.search(r'id="st-post-(\d+)"', raw.get(post.id, ''))
            if m:
                old_ids[int(m.group(1))] = post

        # Pass 2: clean HTML and extract fields.
        for post in posts:
            kind = post.blog_id.eot_kind
            html, meta = self._eot_clean_html(raw.get(post.id, ''), kind, old_ids)
            vals = {
                'eot_words': meta['words'],
                'eot_minutes': max(1, math.ceil(meta['words'] / 200.0)) if meta['words'] else 0,
                'eot_english': meta.get('english') or False,
                'eot_excerpt': meta.get('excerpt') or False,
                'teaser_manual': meta.get('excerpt') or False,
            }
            if kind == 'glossary':
                canon = {fa_sort_key(c): c for c in GLOSSARY_CATEGORIES}
                cats = [canon.get(fa_sort_key(c)) for c in (post.subtitle or '').split('،')]
                cats = [c for c in cats if c]
                vals['eot_topic'] = cats[0] if cats else False
                vals['eot_subtopic'] = meta.get('subcategory') or False
            elif kind == 'articles':
                vals['eot_topic'] = self._eot_article_topic(post.name)
            cr.execute("""
                UPDATE blog_post
                   SET content = (SELECT jsonb_object_agg(k, to_jsonb(%s::text))
                                    FROM jsonb_object_keys(COALESCE(content, '{"en_US": ""}'::jsonb)) k)
                 WHERE id = %s""", [html, post.id])
            post.write(vals)
        posts.invalidate_recordset(['content'])

    @api.model
    def _eot_article_topic(self, name):
        title = (name or '').replace('‌', '')
        for topic, keys in ARTICLE_TOPIC_RULES:
            if any(k.replace('‌', '') in title for k in keys):
                return topic
        return 'روان‌شناسی تعاملی'

    # ------------------------------------------------------------------
    @api.model
    def _eot_clean_html(self, raw, kind, old_ids):
        meta = {'words': 0}
        if not raw or not raw.strip():
            return '', meta
        root = lxml_html.fragment_fromstring(raw, create_parent='div')

        for el in root.xpath('.//*[@data-st-generated]'):
            el.drop_tree()
        for el in root.xpath('.//script | .//style | .//nav[contains(@class, "book-chapter-navigation")]'
                             ' | .//nav[@aria-label="فهرست این صفحه"]'):
            el.drop_tree()

        for el in root.xpath('.//p[contains(@class, "english-equivalent")]'):
            span = el.xpath('.//span')
            meta['english'] = _text(span[0] if span else el).replace('معادل انگلیسی:', '').strip()
            el.drop_tree()
        for el in root.xpath('.//p[contains(@class, "entry-classification")]'):
            txt = _text(el).replace('طبقه‌بندی موضوعی:', '').strip()
            parts = [p.strip() for p in txt.split('،') if p.strip()]
            if len(parts) > 1:
                meta['subcategory'] = parts[-1]
            el.drop_tree()

        for el in root.xpath('.//p'):
            if _text(el) == 'دانلود مقاله':
                el.drop_tree()

        # Known typos from the old import (first letter lost).
        for el in root.iter():
            for attr in ('text', 'tail'):
                val = getattr(el, attr)
                if val and val.lstrip().startswith('رحوزه پرورشی'):
                    setattr(el, attr, val.replace('رحوزه پرورشی', 'در حوزه پرورشی', 1))

        # Links: old-site links -> new URLs, or plain text when unknown.
        for a in root.xpath('.//a[@href]'):
            href = a.get('href') or ''
            for attr in list(a.attrib):
                if attr not in ('href', 'id', 'name'):
                    del a.attrib[attr]
            if 'sepehrtherapy.ir' in href or href.startswith('/blog/'):
                path = unquote(href.split('#')[0].split('?')[0]).rstrip('/')
                m = re.search(r'-(\d+)$', path)
                target = old_ids.get(int(m.group(1))) if m else None
                if target:
                    a.set('href', target.eot_url())
                else:
                    a.drop_tag()

        # Wrappers from the old layout.
        for el in root.xpath('.//article | .//div[contains(@class, "st-body")] | .//dl | .//dd'):
            el.drop_tag()
        for el in list(root):
            if el.tag == 'div' and not el.attrib:
                el.drop_tag()

        # Presentation attributes: the theme styles the content.
        keep_attrs = {'href', 'id', 'dir', 'lang', 'colspan', 'rowspan', 'src', 'alt', 'name', 'start', 'type'}
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            classes = (el.get('class') or '').split()
            for attr in list(el.attrib):
                if attr not in keep_attrs and attr != 'class':
                    del el.attrib[attr]
            kept = [c for c in classes if c == 'contributor']
            if kept:
                el.set('class', ' '.join(kept))
            elif 'class' in el.attrib:
                del el.attrib['class']

        if kind == 'glossary':
            for sec in root.xpath('./section'):
                h2 = sec.xpath('./h2')
                label = _text(h2[0]) if h2 else ''
                if sec.get('lang') == 'en' or label == 'English definition':
                    sec.set('class', 'eot-sec-en')
                    if h2:
                        h2[0].text = 'تعریف انگلیسی'
                        for c in list(h2[0]):
                            h2[0].remove(c)
                        h2[0].set('lang', 'fa')
                        h2[0].set('dir', 'rtl')
                elif label == 'تعریف':
                    sec.set('class', 'eot-sec-def')
                else:
                    sec.set('class', 'eot-sec-more')
            for p in root.xpath('.//p[@class="contributor"]'):
                txt = _text(p)
                p.text = re.sub(r'^نگارنده\s*:\s*', 'نگارنده: ', txt)
                for c in list(p):
                    p.remove(c)

        if kind == 'articles':
            self._eot_promote_headings(root)

        # Section ids for the in-page contents list.
        n = 0
        for h in root.xpath('.//h2'):
            if _text(h) == 'منابع':
                h.set('class', 'eot-refs')
            n += 1
            h.set('id', 's%d' % n)

        for p in root.xpath('.//p'):
            if not _text(p) and not p.xpath('.//img'):
                p.drop_tree()

        text_root = root
        en = root.xpath('.//section[@class="eot-sec-en"]')
        full_text = _text(root)
        en_text = ' '.join(_text(s) for s in en)
        meta['words'] = len(_WORD_RE.findall(full_text)) - len(_WORD_RE.findall(en_text))

        # Excerpt: glossary -> the definition; articles -> abstract or first real paragraph.
        excerpt = ''
        candidates = []
        if kind == 'glossary':
            candidates = text_root.xpath('.//section[@class="eot-sec-def"]//p[not(@class)]') or \
                text_root.xpath('.//p[not(@class)]')
        else:
            heads = text_root.xpath('.//*[self::h2 or self::p][normalize-space(.)="چکیده"]')
            if heads:
                candidates = heads[0].xpath('following-sibling::p')
            candidates = list(candidates) + text_root.xpath('.//p')
        for p in candidates:
            t = _text(p)
            if len(t.split()) >= 12:
                excerpt = t
                break
        meta['excerpt'] = _truncate_words(excerpt, 40) if excerpt else ''

        out = (root.text or '') + ''.join(
            lxml_html.tostring(c, encoding='unicode') for c in root)
        return out.strip(), meta

    @api.model
    def _eot_promote_headings(self, root):
        """Articles have no real headings: short standalone paragraphs act as
        headings. Promote them to <h2> so they get styled and listed."""
        if [h for h in root.xpath('.//h2') if _text(h) not in ('منابع', 'چکیده')]:
            return
        list_marker = re.compile(r'^([0-9۰-۹]+|[؀-ۿ]{1,3})\s*[)\-.]')
        for p in root.xpath('./p'):
            t = _text(p)
            if not (3 <= len(t) <= 70) or len(t.split()) > 10:
                continue
            if t[-1] in '.:؛،!?؟;,' or list_marker.match(t) or re.match(r'^[0-9۰-۹(]', t):
                continue
            nxt = p.getnext()
            if nxt is None or nxt.tag not in ('p', 'ul', 'ol', 'blockquote'):
                continue
            if len(_text(nxt)) <= len(t):
                continue
            p.tag = 'h2'
            p.text = t
            for c in list(p):
                p.remove(c)
