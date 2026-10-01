"""Founder's name with tashdid in data: «دکتر ناصرالدّین کاظمی حقیقی».

Owner's request (2026-10-01): the name is written ناصرالدّین everywhere on the
site. Templates were changed in this version's views; this renames the author
partner (blog.post.author_name follows it) and the book author strings
(blog.blog.eot_authors). URLs keep the old slug. Idempotent.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)
OLD = 'دکتر ناصرالدین کاظمی حقیقی'
NEW = 'دکتر ناصرالدّین کاظمی حقیقی'


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    partners = env['res.partner'].search([('name', 'like', OLD)])
    for p in partners:
        p.name = p.name.replace(OLD, NEW)
    blogs = env['blog.blog'].search([('eot_authors', 'like', OLD)])
    for b in blogs:
        b.eot_authors = b.eot_authors.replace(OLD, NEW)
    _logger.info("eot: founder name with tashdid - %s partner(s), %s book(s)", len(partners), len(blogs))
