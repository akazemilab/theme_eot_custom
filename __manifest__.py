{
    'name': 'EOT Custom Theme',
    'summary': 'Custom website theme for eot.ir (website_id 1 only)',
    'description': """
Custom theme for the eot.ir website (هیجان اندیشه).

Loaded through Odoo's theme mechanism, so its views and assets apply only
to websites whose theme is this module (website_id 1). See README.md.
""",
    'category': 'Theme/Corporate',
    'version': '20.0.9.4.0',
    'author': 'Emotion of Thought Institution',
    'website': 'https://www.eot.ir',
    'license': 'LGPL-3',
    'depends': ['website', 'website_blog', 'auth_signup', 'auth_passkey', 'auth_passkey_portal'],
    'data': [
        'views/theme_marker.xml',
        'views/seo.xml',
        'views/header.xml',
        'views/footer.xml',
        'views/i18n.xml',
        'views/placeholders.xml',
        'views/homepage.xml',
        'views/library.xml',
        'views/footer_links.xml',
        'views/pages_catalog.xml',
        'views/pages_services.xml',
        'views/pages_learning.xml',
        'views/pages_trust.xml',
        'views/pages_legal.xml',
        'data/library_sync.xml',
    ],
    'assets': {
        # Theme-level SCSS variables (colors, fonts, spacing). Loaded before
        # Bootstrap/website variables so values set here win.
        'web._assets_primary_variables': [
            'theme_eot_custom/static/src/scss/primary_variables.scss',
        ],
        # Theme styles. Only bundled for websites using this theme.
        'web.assets_frontend': [
            'theme_eot_custom/static/src/scss/theme.scss',
            'theme_eot_custom/static/src/scss/library.scss',
            'theme_eot_custom/static/src/scss/pages.scss',
            'theme_eot_custom/static/src/js/library.js',
            'theme_eot_custom/static/src/xml/user_switch_fa.xml',
        ],
    },
    'installable': True,
    'application': False,
}
