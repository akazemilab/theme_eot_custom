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
from odoo import models
from odoo.http import request

from .library import WEBSITE_ID
from .fa_text import fa_slug_text, fa_fold_letters  # noqa: F401 (re-exported)

FOUNDER = 'دکتر ناصرالدین کاظمی حقیقی'
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
