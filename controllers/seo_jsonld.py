"""Schema.org JSON-LD for the eot.ir library pages (website 1).

Every value comes from what the page itself shows: titles, the byline
(book authors / the founder for articles and glossary entries), the
visible breadcrumb trail, English equivalents on glossary entries and the
visible description.  Publication dates are left out on purpose: the
records' dates are import timestamps, not real publication dates.
"""
import json

from odoo.http import request

from ..models.seo import FOUNDER, FOUNDER_URL, share_image_url


def _base():
    return (request.env.website.domain or request.httprequest.url_root).rstrip('/')


def _abs(path):
    return _base() + path


def _org_ref():
    return {'@id': _base() + '/#organization'}


def _person(name):
    person = {'@type': 'Person', 'name': name}
    if name == FOUNDER:
        person['url'] = _abs(FOUNDER_URL)
    return person


def _authors(text):
    text = (text or FOUNDER).strip()
    if text == FOUNDER:
        return [_person(FOUNDER)]
    # "A و B" / "A، B، C" -> several people (as printed in the byline)
    parts = [p.strip() for p in text.replace(' و ', '،').split('،') if p.strip()]
    return [_person(p) for p in parts] or [_person(FOUNDER)]


def breadcrumb(items):
    """items: [(name, path), ...] exactly as the visible trail shows them."""
    return {
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': i, 'name': name, 'item': _abs(path)}
            for i, (name, path) in enumerate(items, 1)
        ],
    }


def render(*schemas):
    website = request.env.website
    graph = [website._prepare_jsonld_vals()] + [s for s in schemas if s]
    return json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False)


def book(blog, chapter_count=None):
    vals = {
        '@type': 'Book',
        '@id': _abs(blog.eot_url()) + '#book',
        'name': blog.name,
        'url': _abs(blog.eot_url()),
        'author': _authors(blog.eot_authors),
        'inLanguage': 'fa',
        'publisher': _org_ref(),
        'image': share_image_url(request.env),
        'isAccessibleForFree': True,
    }
    if blog.eot_subtitle:
        vals['alternativeHeadline'] = blog.eot_subtitle
    if blog.eot_description:
        vals['description'] = blog.eot_description
    return vals


def chapter(post, blog):
    title = post.eot_title or post.name
    return {
        '@type': 'Article',
        'headline': title[:110],
        'url': _abs(post.eot_url()),
        'mainEntityOfPage': _abs(post.eot_url()),
        'author': _authors(blog.eot_authors),
        'publisher': _org_ref(),
        'inLanguage': 'fa',
        'image': share_image_url(request.env),
        'isPartOf': {'@id': _abs(blog.eot_url()) + '#book', '@type': 'Book', 'name': blog.name},
        'isAccessibleForFree': True,
    }


def article(post):
    vals = {
        '@type': 'Article',
        'headline': (post.eot_title or post.name)[:110],
        'url': _abs(post.eot_url()),
        'mainEntityOfPage': _abs(post.eot_url()),
        'author': [_person(post.author_name or FOUNDER)],
        'publisher': _org_ref(),
        'inLanguage': 'fa',
        'image': share_image_url(request.env),
        'isAccessibleForFree': True,
    }
    if post.eot_excerpt:
        vals['description'] = post.eot_excerpt
    if post.eot_topic:
        vals['articleSection'] = post.eot_topic
    if post.eot_words:
        vals['wordCount'] = post.eot_words
    return vals


def term_set(blog):
    return {
        '@type': 'DefinedTermSet',
        '@id': _abs('/فرهنگنامه') + '#set',
        'name': blog.name,
        'url': _abs('/فرهنگنامه'),
        'description': blog.eot_description or '',
        'inLanguage': 'fa',
        'publisher': _org_ref(),
    }


def term(post, english):
    vals = {
        '@type': 'DefinedTerm',
        'name': post.eot_title or post.name,
        'url': _abs(post.eot_url()),
        'inDefinedTermSet': {'@id': _abs('/فرهنگنامه') + '#set'},
        'inLanguage': 'fa',
    }
    if english:
        vals['alternateName'] = english
    if post.eot_excerpt:
        vals['description'] = post.eot_excerpt
    return vals


def collection(name, path, description=''):
    vals = {'@type': 'CollectionPage', 'name': name, 'url': _abs(path), 'inLanguage': 'fa'}
    if description:
        vals['description'] = description
    return vals
