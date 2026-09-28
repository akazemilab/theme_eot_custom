"""Milestone 8 data changes on website 1. Idempotent; website 1 only.

1. Remove the redirect rule that forces /web/reset_password to 404.
   It came from a bulk "SEO 5xx legacy cleanup" (2026-09-25) - the page was
   erroring on the old server - but the sign-in page still links to it and
   auth_signup.reset_password is enabled. The owner approved removing it.
   Only that exact rule is touched: url_from, redirect_type and website are
   all asserted, and anything unexpected aborts the upgrade loudly.

2. Add "خدمات" (/خدمات) and "درباره ما" (/about) to the top menu, after
   the existing library items, the same way those are stored (manual_url).
   Before this, services and trust pages were reachable only from the
   footer. Skipped for any url already in website 1's menu.

3. Persian names for the account-portal tiles (portal.entry records from
   the portal / portal_discuss modules). Odoo 20's fa.po has no entry for
   these names, so the tiles showed "Addresses", "Connection & Security",
   "Discuss". Matched by url, only the fa_IR key is added.

4. Persian record names for the two published pages still named in English
   (/about "About", /contactus "Contact Us"). The name shows in site search
   results; the browser titles were already Persian. Wording taken from each
   page's own Persian title.
"""

PORTAL_ENTRY_FA = {
    # url: (name, description or None to leave as is)
    '/my/addresses': ('نشانی‌ها', None),
    '/my/security': ('ارتباط و امنیت', None),
    '/my/conversations': ('گفتگوها', 'دسترسی به گفتگوهای شما'),
}

PAGE_NAME_FA = {
    '/about': 'درباره هیجان اندیشه',
    '/contactus': 'تماس با هیجان اندیشه',
}

MENU_ITEMS = [
    # (url, label, sequence)
    ('/خدمات', 'خدمات', 23),
    ('/about', 'درباره ما', 24),
]


def migrate(cr, version):
    # 1. reset-password 404 rule ------------------------------------------
    cr.execute(
        """
        SELECT id, url_from, redirect_type, website_id
          FROM website_rewrite
         WHERE url_from = '/web/reset_password'
        """
    )
    rows = cr.fetchall()
    for rid, url_from, rtype, website_id in rows:
        if rtype != '404' or website_id != 1:
            raise Exception(
                "milestone 8: unexpected /web/reset_password rewrite %s "
                "(type %s, website %s) - refusing to touch it" % (rid, rtype, website_id)
            )
    if rows:
        cr.execute(
            """
            DELETE FROM website_rewrite
             WHERE url_from = '/web/reset_password'
               AND redirect_type = '404'
               AND website_id = 1
            """
        )

    # 2. top menu items -----------------------------------------------------
    cr.execute(
        """
        SELECT id, parent_path FROM website_menu
         WHERE website_id = 1 AND parent_id IS NULL
         ORDER BY id LIMIT 1
        """
    )
    top = cr.fetchone()
    if not top:
        raise Exception("milestone 8: website 1 has no top menu")
    top_id, top_path = top

    for url, label, sequence in MENU_ITEMS:
        cr.execute(
            """
            SELECT m.id FROM website_menu m
              LEFT JOIN website_page p ON p.id = m.page_id
             WHERE m.website_id = 1
               AND (m.manual_url = %s OR p.url->>'en_US' = %s)
            """,
            (url, url),
        )
        if cr.fetchone():
            continue
        cr.execute(
            """
            INSERT INTO website_menu
                   (name, manual_url, parent_id, website_id, sequence, new_window,
                    create_uid, write_uid, create_date, write_date)
            VALUES (jsonb_build_object('en_US', %s::text, 'fa_IR', %s::text),
                    %s, %s, 1, %s, false, 1, 1, now() at time zone 'UTC', now() at time zone 'UTC')
            RETURNING id
            """,
            (label, label, url, top_id, sequence),
        )
        new_id = cr.fetchone()[0]
        cr.execute(
            "UPDATE website_menu SET parent_path = %s WHERE id = %s",
            ("%s%s/" % (top_path, new_id), new_id),
        )

    # 3. portal tile names ----------------------------------------------------
    for url, (name, desc) in PORTAL_ENTRY_FA.items():
        cr.execute(
            "UPDATE portal_entry SET name = name || jsonb_build_object('fa_IR', %s::text) WHERE url = %s",
            (name, url),
        )
        if desc:
            cr.execute(
                """
                UPDATE portal_entry
                   SET description = COALESCE(description, '{}'::jsonb) || jsonb_build_object('fa_IR', %s::text)
                 WHERE url = %s
                """,
                (desc, url),
            )

    # 4. page record names ----------------------------------------------------
    for url, name in PAGE_NAME_FA.items():
        cr.execute(
            """
            UPDATE website_page
               SET name = name || jsonb_build_object('fa_IR', %s::text)
             WHERE website_id = 1 AND url->>'en_US' = %s
            """,
            (name, url),
        )
