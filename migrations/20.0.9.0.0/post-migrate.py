"""SEO milestone data changes on website 1 (docs/seo_audit_2026-09-29.md).

1. Repair the old-site redirect map (website.rewrite, website 1, type 301).
   Its targets were written against an older database whose blog/post ids
   have since been reused: every /blog/resources-20/... article landed on
   the book «استعداد ریاضی», glossary terms landed on unrelated book
   chapters, and the booking URLs pointed at /appointment (uninstalled).
   Each old post URL is now matched BY TITLE (its own slug, then the title
   in its old target) to a current published library item and pointed at
   that item's canonical URL; old URLs with no counterpart become 404
   (owner decision 2026-09-29: the ~200 articles that no longer exist are
   not redirected elsewhere). Listing/pagination/booking URLs get explicit
   targets, all asserted to exist before anything is written.
2. A few old URLs that still get search impressions and had no rule.
3. Drop website 1's cached sitemap so it regenerates with https:// URLs,
   without the feed URLs and with the normalised Persian slugs (pitfall #16).

Idempotent. Website 1 only - any rule on another website is untouched.
Set EOT_DRY_RUN=1 to print the report and roll back.
"""
import logging
import os
import re
from collections import Counter, defaultdict
from urllib.parse import unquote

from odoo import SUPERUSER_ID, api

from odoo.addons.theme_eot_custom.models.fa_text import fa_match_key

_logger = logging.getLogger(__name__)

WEBSITE_ID = 1
CONSULT = '/مشاوره-روانشناسی-آنلاین'
FOUNDER = '/دکتر-ناصرالدین-کاظمی-حقیقی'

# Exact old URL -> new target (page paths, or 'book:<name>' resolved below).
EXACT = {
    '/appointment/4': CONSULT,
    '/psychology-clinic': CONSULT,
    '/book-session': CONSULT,
    '/khdh-nwbt-mshwrh': CONSULT,
    '/book-session/dr-kazemi-haghighi': CONSULT,
    '/site/blog/posts': '/مقالات',
    '/shop/basic-growth-plan-8': '/خدمات',
    '/product-116': '/خدمات',
    '/forum/راهنما-2': '/سوالات-متداول',
    '/courses': '/کلاس-گروهی-آنلاین',
    '/روانشناسی-فرهنگی-بررسی-تعامل-انسان-با-فرهنگ': 'book:روانشناسی فرهنگی',
}
# Old URLs with search impressions and no rule yet -> target.
NEW_RULES = {
    '/appointment': CONSULT,
    '/drkazemi': FOUNDER,
    '/shop/category/دورههای-تخصصی-2': '/یادگیری-خودیار-روانشناسی',
    '/blog/هیجان-اندیشه-22': 'book:هیجان اندیشه',
}
LISTING = [
    (re.compile(r'^/blog/resources-20(/page/\d+)?/?$'), '/مقالات'),
    (re.compile(r'^/blog/glossary-15(/page/\d+)?/?$'), '/فرهنگنامه'),
    (re.compile(r'^/blog/مقالات-21(/page/\d+)?/?$'), '/مقالات'),
]
KIND_PREFERENCE = {
    'glossary-15': ('glossary', 'articles', 'book'),
    None: ('articles', 'book', 'glossary'),
}


def _strip_id(segment):
    return re.sub(r'-\d+$', '', unquote(segment or ''))


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'lang': 'fa_IR'})
    dry = os.environ.get('EOT_DRY_RUN') == '1'
    Rewrite = env['website.rewrite'].with_context(active_test=False)

    # ---- targets that must exist ----------------------------------------
    blogs = env['blog.blog'].search([('website_id', '=', WEBSITE_ID), ('eot_kind', '!=', False)])
    books = {fa_match_key(b.name): b.eot_url() for b in blogs if b.eot_kind == 'book'}
    pages = set(env['website.page'].search(
        [('website_id', 'in', (WEBSITE_ID, False)), ('is_published', '=', True)]).mapped('url'))
    static_ok = pages | {'/مقالات', '/فرهنگنامه', '/کتب'}

    def resolve(target):
        if target.startswith('book:'):
            url = books.get(fa_match_key(target[5:]))
            if not url:
                raise Exception('SEO migration: no book named %r - refusing to continue' % target[5:])
            return url
        if target not in static_ok:
            raise Exception('SEO migration: target %r is not a published page on website 1' % target)
        return target

    exact = {k: resolve(v) for k, v in EXACT.items()}
    new_rules = {k: resolve(v) for k, v in NEW_RULES.items()}

    # ---- title index of current library items ----------------------------
    posts = env['blog.post'].search([('blog_id', 'in', blogs.ids), ('is_published', '=', True)])
    by_key = defaultdict(list)
    for p in posts:
        for text in {p.eot_title or '', p.name or ''}:
            key = fa_match_key(text)
            if key:
                by_key[key].append(p)

    def match(keys, prefs):
        for key in keys:
            cands = sorted(set(by_key.get(key, [])), key=lambda p: p.id)
            if len(cands) == 1:
                return cands[0], 'title'
            if cands:
                for kind in prefs:
                    same = [p for p in cands if p.blog_id.eot_kind == kind]
                    if same:
                        return same[0], 'title+kind'
        return None, 'no-match'

    # ---- walk website 1's 301 rules -------------------------------------
    rules = Rewrite.search([('website_id', '=', WEBSITE_ID), ('redirect_type', '=', '301')])
    stats = Counter()
    changes = []  # (rule, vals)
    for rule in rules:
        src = rule.url_from or ''
        vals = None
        if src in exact:
            vals = {'url_to': exact[src]}; stats['exact'] += 1
        elif any(rx.match(src) for rx, _t in LISTING):
            target = next(t for rx, t in LISTING if rx.match(src))
            vals = {'url_to': target}; stats['listing'] += 1
        else:
            segs = [s for s in src.split('/') if s]
            if src.startswith('/blog/') and len(segs) >= 3 and segs[2] not in ('page', 'tag', 'feed'):
                dsegs = [s for s in (rule.url_to or '').split('/') if s]
                keys = [fa_match_key(_strip_id(segs[-1]))]
                if len(dsegs) >= 3:
                    keys.append(fa_match_key(_strip_id(dsegs[-1])))
                prefs = KIND_PREFERENCE.get(segs[1], KIND_PREFERENCE[None])
                post, how = match([k for k in keys if k], prefs)
                if post:
                    vals = {'url_to': post.eot_url()}
                else:
                    vals = {'redirect_type': '404', 'url_to': False}
                stats[how] += 1
            else:
                stats['kept'] += 1
        if vals and any(rule[k] != v for k, v in vals.items()):
            changes.append((rule, vals))

    existing = set(Rewrite.search([('website_id', '=', WEBSITE_ID)]).mapped('url_from'))
    to_create = [{'name': 'SEO milestone: %s' % src, 'url_from': src, 'url_to': dst,
                  'redirect_type': '301', 'website_id': WEBSITE_ID}
                 for src, dst in new_rules.items() if src not in existing]

    # ---- sanity: a sane share of old posts must have found their page ----
    matched = stats['title'] + stats['title+kind']
    if rules and matched < 150:
        raise Exception('SEO migration: only %d old posts matched by title (expected ~228) - '
                        'refusing to rewrite the redirect map' % matched)

    _logger.info('SEO migration: %d rules on website 1: %s; %d to change, %d to create%s',
                 len(rules), dict(stats), len(changes), len(to_create), ' (DRY RUN)' if dry else '')
    for rule, vals in changes[:8]:
        _logger.info('  %s -> %s', rule.url_from, vals)

    if dry:
        raise Exception('EOT_DRY_RUN=1: report above, nothing written')

    for rule, vals in changes:
        rule.write(vals)
    if to_create:
        Rewrite.create(to_create)

    # ---- 3. cached sitemap (website 1 only) ------------------------------
    stale = env['ir.attachment'].search([('url', '=like', '/sitemap%'), ('website_id', '=', WEBSITE_ID)])
    other = env['ir.attachment'].search_count([('url', '=like', '/sitemap%'), ('website_id', '!=', WEBSITE_ID)])
    stale.unlink()
    _logger.info('SEO migration: dropped %d cached sitemap rows of website 1 (%d of other websites untouched)',
                 len(stale), other)
