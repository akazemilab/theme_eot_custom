"""Preview of the Odoo-rendered error pages (views/errors.xml, i18n.xml).
Always answers 200 + noindex so the page can be looked at without causing a
real error; static nginx pages are listed in /theme_eot_custom/static/errors/."""
from odoo import http
from odoo.http import request

MESSAGES = {400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found', 405: 'Method Not Allowed',
            422: 'Unprocessable Entity', 429: 'Too Many Requests', 500: 'Internal Server Error'}
TEMPLATES = {400: 'http_routing.400', 403: 'http_routing.403', 404: 'http_routing.404',
             500: 'http_routing.500'}


class EotErrorPreview(http.Controller):

    @http.route('/error-preview', type='http', auth='public', website=True, sitemap=False)
    def index(self, **kw):
        return request.redirect('/theme_eot_custom/static/errors/index.html')

    @http.route('/error-preview/<int:code>', type='http', auth='public', website=True, sitemap=False)
    def show(self, code, **kw):
        tpl = TEMPLATES.get(code, 'http_routing.http_error')
        values = {'status_code': code, 'status_message': MESSAGES.get(code, 'Error'),
                  'exception': None, 'qweb_exception': None, 'traceback': None}
        response = request.render(tpl, values)
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
