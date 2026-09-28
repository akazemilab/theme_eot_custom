"""Publish the milestone-6 pages on website 1.

The redesigned pages (services, trust & method, legal, /about, /contactus)
existed as unpublished builder pages. Once the theme templates for them are
loaded, they are published. Idempotent. Website 1 only.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE website_page p
           SET is_published = true
          FROM ir_model_data d
         WHERE d.module = 'theme_eot_custom'
           AND d.name LIKE 'eot\\_pv\\_%%'
           AND d.model = 'ir.ui.view'
           AND p.view_id = d.res_id
           AND p.website_id = 1
           AND p.is_published IS NOT TRUE
        """
    )
