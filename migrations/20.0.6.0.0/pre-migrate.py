"""Give the milestone-6 page views the external ids the theme inherits from.

Same mechanism as migrations/20.0.3.0.1 (homepage): these pages are
builder-made views with no external id of their own, so
<template inherit_id="..."> cannot target them. Each one is looked up by
its key (and website), and named theme_eot_custom.eot_pv_<name>.
Idempotent (insert only when missing); noupdate=True so the module's
end-of-upgrade cleanup never deletes the id or the view it points at.

website_id None means the generic view (the stock contact thank-you page),
which the theme then extends for website 1 only.
"""

VIEWS = [
    # (xml name, view key, website_id)
    ("eot_pv_services", "website.eot_services_hub_20260921", 1),
    ("eot_pv_counseling", "website.eot_online_psychology_appointment_20260920", 1),
    ("eot_pv_classes", "website.eot_online_group_classes_20260921", 1),
    ("eot_pv_internship", "website.eot_psychology_internship_program_20260921", 1),
    ("eot_pv_learning", "website.مرکز-یادگیری-انلاین-روانشناسی", 1),
    ("eot_pv_assessments", "website.eot_psychological_assessments_hub_20260920", 1),
    ("eot_pv_founder", "website.eot_public_264935e462_20260921", 1),
    ("eot_pv_about", "website.about", 1),
    ("eot_pv_editorial", "website.eot_public_c2caed648e_20260921", 1),
    ("eot_pv_safety", "website.eot_public_444979d729_20260921", 1),
    ("eot_pv_method", "website.eot_public_04800e0735_20260921", 1),
    ("eot_pv_faq", "website.eot_public_e8593f5b1d_20260921", 1),
    ("eot_pv_siteguide", "website.eot_public_d7c45f31ff_20260921", 1),
    ("eot_pv_privacy", "website.eot_public_f75e8507b8_20260921", 1),
    ("eot_pv_terms", "website.eot_public_d74ef9ca37_20260921", 1),
    ("eot_pv_cookie", "website.eot_public_d272dd5ef3_20260921", 1),
    ("eot_pv_access", "website.eot_public_6e43556c86_20260921", 1),
    ("eot_pv_contact", "website.contactus", 1),
    ("eot_pv_thanks", "website.contactus_thanks", None),
]


def migrate(cr, version):
    for name, key, website_id in VIEWS:
        cr.execute(
            """
            INSERT INTO ir_model_data (module, name, model, res_id, noupdate)
            SELECT 'theme_eot_custom', %s, 'ir.ui.view', v.id, true
              FROM ir_ui_view v
             WHERE v.key = %s
               AND v.website_id IS NOT DISTINCT FROM %s
               AND NOT EXISTS (
                    SELECT 1 FROM ir_model_data
                     WHERE module = 'theme_eot_custom' AND name = %s
               )
             ORDER BY v.id
             LIMIT 1
            """,
            (name, key, website_id, name),
        )
