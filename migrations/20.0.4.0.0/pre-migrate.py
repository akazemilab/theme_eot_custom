"""Remove English (en_US) as an active language on website 1.

Owner's request: "remove english version entirely" - the /en prefix, the
language switcher's "English (US)" entry, and the fa_IR/en_US split should
go away for eot.ir. Website 1 keeps fa_IR only.

Scope: only website_id=1's row in website_lang_rel. Website 3
(sepehrtherapy duplicate) is untouched - it keeps its own en_US row, and
the res.lang record itself is left active (other websites, and Odoo's own
backend, still use it).

Idempotent: a DELETE of a row that no longer exists is a no-op, so this is
safe to run on every upgrade.
"""

WEBSITE_ID = 1


def migrate(cr, version):
    cr.execute(
        """
        DELETE FROM website_lang_rel
         WHERE website_id = %s
           AND lang_id = (SELECT id FROM res_lang WHERE code = 'en_US')
        """,
        (WEBSITE_ID,),
    )
    # If the site's default language ever ended up pointing at en_US, put
    # it back on fa_IR so nothing 500s trying to render a removed default.
    cr.execute(
        """
        UPDATE website
           SET default_lang_id = (SELECT id FROM res_lang WHERE code = 'fa_IR')
         WHERE id = %s
           AND default_lang_id = (SELECT id FROM res_lang WHERE code = 'en_US')
        """,
        (WEBSITE_ID,),
    )
