"""SEO helpers for eot.ir (website 1 only).

- fa_slug_text(): normalises Persian text before it becomes a URL slug:
  drops diacritics (tashdid, fatha, hamza-above ...), folds hamza carriers
  and Arabic letter forms to their plain Persian letters, and removes a
  leading chapter number ("3- ", "12. ").  Old slugs keep working: every
  library route looks items up by their trailing id and 301s any other
  slug to the canonical one.
- Share image and description defaults for library books/posts, whose
  Odoo defaults were an empty og:image ("https://www.eot.ir") and no
  meta description.
- Organization / WebSite JSON-LD enrichment, using only facts that are
  shown on the site (contact page, homepage, founder page).
"""
import re
from urllib.parse import quote, unquote

from werkzeug.exceptions import NotFound
from werkzeug.routing import RequestRedirect

from odoo import models
from odoo.http import request

from .library import WEBSITE_ID
from .fa_text import fa_fold_letters, fa_match_key, fa_slug_text  # noqa: F401 (re-exported)

FOUNDER = 'دکتر ناصرالدّین کاظمی حقیقی'


def is_founder(name):
    """True for the founder's name with or without the tashdid on «ناصرالدّین»."""
    return (name or '').replace('\u0651', '').strip() == FOUNDER.replace('\u0651', '')
FOUNDER_URL = '/دکتر-ناصرالدین-کاظمی-حقیقی'

def _on_site(env):
    website = env.website
    return bool(website) and website.id == WEBSITE_ID


def share_image_url(env):
    website = env.website
    field = 'social_default_image' if website.has_social_default_image else 'logo'
    return website.image_url(website, field)


class BlogBlogSeo(models.Model):
    _inherit = 'blog.blog'

    def _default_website_meta(self):
        res = super()._default_website_meta()
        if _on_site(self.env) and self.eot_kind:
            desc = (self.eot_description or self.subtitle or '').strip()
            if desc:
                res['default_meta_description'] = desc
                res['default_opengraph']['og:description'] = desc
            image = share_image_url(self.env)
            res['default_opengraph']['og:image'] = image
            res['default_twitter']['twitter:image'] = image
        return res


class BlogPostSeo(models.Model):
    _inherit = 'blog.post'

    def _default_website_meta(self):
        res = super()._default_website_meta()
        if _on_site(self.env) and self.blog_id.eot_kind:
            og = res['default_opengraph']
            # Odoo takes og:image from the cover; library posts have none, which
            # produced the bare domain as the image.
            if not og.get('og:image') or og['og:image'] in ('none', ''):
                og['og:image'] = share_image_url(self.env)
            res['default_twitter']['twitter:image'] = og['og:image']
            og['og:title'] = self.eot_title or self.name
            if not res.get('default_meta_description') and self.eot_excerpt:
                res['default_meta_description'] = self.eot_excerpt
                og['og:description'] = self.eot_excerpt
            # Import timestamps, not real publication dates: don't claim them.
            og.pop('article:published_time', None)
            og.pop('article:modified_time', None)
        return res


class WebsiteSeo(models.Model):
    _inherit = 'website'

    def _prepare_jsonld_vals(self):
        vals = super()._prepare_jsonld_vals()
        if self.id == WEBSITE_ID and vals:
            base = (self.domain or '').rstrip('/')
            vals.update({
                'alternateName': ['مؤسسه تعاملی هیجان اندیشه', 'EOT'],
                'founder': {'@type': 'Person', 'name': FOUNDER, 'url': base + FOUNDER_URL},
                'email': 'info@eot.ir',
                'contactPoint': {
                    '@type': 'ContactPoint', 'contactType': 'customer support',
                    'telephone': '+98-21-88174100', 'email': 'info@eot.ir',
                    'availableLanguage': 'fa', 'url': base + '/contactus',
                },
            })
        return vals

    def _get_jsonld_dict(self, is_detail_page=False):
        schemas = super()._get_jsonld_dict(is_detail_page=is_detail_page)
        if (self.id == WEBSITE_ID and request and request.httprequest
                and request.httprequest.path in ('/', '')):
            base = (self.domain or '').rstrip('/')
            schemas.append({
                '@type': 'WebSite', '@id': base + '/#website', 'url': base + '/',
                'name': self.name, 'inLanguage': 'fa-IR',
                'publisher': {'@id': base + '/#organization'},
            })
        return schemas


class _Moved(RequestRedirect):
    code = 301


class IrHttpSeo(models.AbstractModel):
    """Old-site /blog/... URLs on eot.ir carry record ids that now belong to
    OTHER books and posts (the database was rebuilt), e.g. /blog/خلاقیت-31
    is today the id of «آموزش و پرورش برای استعداد و تیزهوشی». Werkzeug
    fixes a wrong slug by redirecting to the id's record *before* any
    controller runs, which sent visitors and Google to the wrong book.

    So on website 1, before routing: when the name in a /blog/ URL does not
    match the record behind its id, send the request to the library item
    with that name, or - if there is none - on to the normal fallback
    (website.rewrite rules, then 404). Never to another record's page."""
    _inherit = 'ir.http'

    @classmethod
    def _match(cls, path_info):
        # super() first: http_routing's _match sets request.lang, which the
        # 404 fallback needs. Werkzeug's own slug-fix redirect (RequestRedirect)
        # and "no route" (NotFound) are re-examined before they are raised.
        try:
            res = super()._match(path_info)
        except (RequestRedirect, NotFound):
            cls._eot_blog_guard(path_info)
            raise
        cls._eot_blog_guard(path_info)
        return res

    @classmethod
    def _eot_blog_guard(cls, path_info):
        if path_info.startswith('/blog/') and request and request.env.context.get('host_id') == WEBSITE_ID:
            target = cls._eot_blog_target(path_info)
            if target is False:
                raise NotFound()
            if target:
                raise _Moved(quote(target, safe='/'))

    @classmethod
    def _eot_blog_target(cls, path_info):
        """None: route normally. False: no such item. str: redirect there."""
        parts = [p for p in unquote(path_info).split('/') if p]
        if len(parts) < 2:
            return None
        env = request.env(su=True)
        strip = lambda seg: re.sub(r'-\d+$', '', seg)
        rid = lambda seg: int(re.search(r'-(\d+)$', seg).group(1)) if re.search(r'-(\d+)$', seg) else None
        blog_id = rid(parts[1])
        if blog_id is None:
            return None
        blog = env['blog.blog'].with_context(lang='fa_IR').browse(blog_id).exists()
        library = env['blog.blog'].with_context(lang='fa_IR').search(
            [('website_id', '=', WEBSITE_ID), ('eot_kind', '!=', False)])
        post_like = len(parts) >= 3 and parts[2] not in ('page', 'tag', 'feed')
        if not post_like:
            key = fa_match_key(strip(parts[1]))
            if blog and key in (fa_match_key(blog.name), fa_match_key(blog.seo_name or '')):
                return None
            if blog and not blog.eot_kind and blog.website_id.id not in (False, WEBSITE_ID):
                return None
            if len(parts) >= 3 and parts[2] == 'feed':
                return False
            same = library.filtered(lambda b: fa_match_key(b.name) == key)[:1]
            return same.eot_url() if same else False
        post_id = rid(parts[2])
        if post_id is None:
            return None
        post = env['blog.post'].with_context(lang='fa_IR').browse(post_id).exists()
        key = fa_match_key(strip(parts[2]))
        if post and key in (fa_match_key(post.eot_title or ''), fa_match_key(post.name),
                            fa_match_key(post.seo_name or '')):
            return None
        if post and not post.blog_id.eot_kind:
            return None
        posts = env['blog.post'].with_context(lang='fa_IR').search(
            [('blog_id', 'in', library.ids), ('is_published', '=', True)])
        found = posts.filtered(lambda p: key in (fa_match_key(p.eot_title or ''), fa_match_key(p.name)))
        if len(found) > 1 and 'glossary' in parts[1]:
            found = found.filtered(lambda p: p.blog_id.eot_kind == 'glossary') or found
        found = found.sorted('id')[:1]
        return found.eot_url() if found else False


class WebsitePageSeo(models.Model):
    """Odoo 20 caches anonymous website.page HTML keyed only by website, lang,
    cookies flag, path and debug (website_page._get_cache_key). But the <head>
    of that HTML depends on the request host: website.layout adds
    <meta name="robots" content="noindex"> when the host is not the website
    domain (odoo.innerquest.me, 127.0.0.1), and data-tracking-enabled depends on
    bot detection. One render on the admin host was then served, noindex and
    all, to www.eot.ir visitors and Googlebot for up to an hour. Keying the
    cache by host root and bot flag keeps those renders apart (all websites)."""
    _inherit = 'website.page'

    def _get_cache_key(self, request):
        return super()._get_cache_key(request) + (
            request.httprequest.url_root,
            request.env['ir.http'].is_a_bot(),
        )
