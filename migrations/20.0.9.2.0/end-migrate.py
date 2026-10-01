"""Drop stale fa_IR copies of theme view archs (website 1).

The theme's source text is already Persian (stored under en_US). A view that
was edited in the database (website editor / RPC) got its own fa_IR copy, and
on later theme upgrades Odoo keeps "similar" old fa_IR terms - so small text
fixes (tashdid, joined «بنیانگذار») never reached the site. Removing the fa_IR
key makes Persian visitors read the en_US source again.

Idempotent; theme_eot_custom.* views only.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    cr.execute("""
        UPDATE ir_ui_view
           SET arch_db = arch_db - 'fa_IR' - '_en_US'
         WHERE key LIKE 'theme_eot_custom.%%'
           AND (arch_db ? 'fa_IR' OR arch_db ? '_en_US')
     RETURNING id, key
    """)
    for vid, key in cr.fetchall():
        _logger.info("eot: dropped stale fa_IR arch copy of view %s (%s)", vid, key)
