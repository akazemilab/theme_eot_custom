"""Permanent redirects for URLs retired in milestone 6.

These have to be controller routes rather than website.rewrite records:
Odoo serves an existing website.page before it looks at redirect records,
and some of these URLs are still stock/generic pages (e.g. /privacy is the
website module's own privacy stub). A route is matched before any page.

    /privacy                      -> /حریم-خصوصی (the real policy)
    /courses, /courses/...        -> /کلاس-گروهی-آنلاین (old course pages,
                                     which errored in Odoo 20)
    /your-ticket-has-been-submitted, /your-task-has-been-submitted
                                  -> /contactus (helpdesk/project are not
                                     installed; nothing leads there)
    /my/psychological-results     -> /آزمون-روانشناسی (demo results page of
                                     an uninstalled module)
"""
from urllib.parse import quote

from odoo import http
from odoo.http import request

PRIVACY = "/حریم-خصوصی"
CLASSES = "/کلاس-گروهی-آنلاین"
ASSESSMENTS = "/آزمون-روانشناسی"
CONTACT = "/contactus"


def _go(path):
    return request.redirect(quote(path), code=301, local=True)


class EotRetiredUrls(http.Controller):

    @http.route(["/privacy"], type="http", auth="public", website=True, sitemap=False)
    def eot_privacy(self, **kw):
        return _go(PRIVACY)

    @http.route(["/courses", "/courses/<path:rest>"], type="http", auth="public", website=True, sitemap=False)
    def eot_courses(self, rest=None, **kw):
        return _go(CLASSES)

    @http.route(["/your-ticket-has-been-submitted", "/your-task-has-been-submitted"],
                type="http", auth="public", website=True, sitemap=False)
    def eot_submitted(self, **kw):
        return _go(CONTACT)

    @http.route(["/my/psychological-results"], type="http", auth="public", website=True, sitemap=False)
    def eot_psy_results(self, **kw):
        return _go(ASSESSMENTS)
