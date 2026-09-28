"""Ensure website 1's homepage view has the external id the theme inherits from.

views/homepage.xml inherits from theme_eot_custom.eot_home_view_ref. Website
1's homepage is a standalone builder page (key "website.خانه") with no
external id of its own, so this names it. Idempotent: inserts only when the
id is missing. noupdate=True keeps Odoo's end-of-upgrade cleanup from ever
deleting the id - or the homepage view it points at.
"""

HOME_KEY = "website.خانه"
WEBSITE_ID = 1


def migrate(cr, version):
    cr.execute(
        """
        INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
        SELECT 'theme_eot_custom', 'eot_home_view_ref', 'ir.ui.view', v.id, true
          FROM ir_ui_view v
         WHERE v.key = %s
           AND v.website_id = %s
           AND NOT EXISTS (
                SELECT 1 FROM ir_model_data
                 WHERE module = 'theme_eot_custom'
                   AND name = 'eot_home_view_ref'
           )
         ORDER BY v.id
         LIMIT 1
        """,
        (HOME_KEY, WEBSITE_ID),
    )
