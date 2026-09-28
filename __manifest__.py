{
    'name': 'EOT Custom Theme',
    'summary': 'Custom website theme for eot.ir (website_id 1 only)',
    'description': """
Custom theme for the eot.ir website (هیجان اندیشه).

Loaded through Odoo's theme mechanism, so its views and assets apply only
to websites whose theme is this module (website_id 1). See README.md.
""",
    'category': 'Theme/Corporate',
    'version': '20.0.1.0.0',
    'author': 'Emotion of Thought Institution',
    'website': 'https://www.eot.ir',
    'license': 'LGPL-3',
    'depends': ['website'],
    'data': [
        'views/theme_marker.xml',
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
        ],
    },
    'installable': True,
    'application': False,
}
