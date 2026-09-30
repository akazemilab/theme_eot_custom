# theme_eot_custom — working rules

Odoo 20 theme for eot.ir (website_id 1, db eot_main, server eot-odoo-prod
95.38.235.225). Read README.md for the scoping mechanism and deploy script.

## Facts that change how you work
- **Deploys are LIVE.** www.eot.ir, eot.ir and odoo.innerquest.me all serve
  from eot-odoo-prod. There is no staging copy. A milestone branch deployed
  "for review" is public. Verify immediately after every deploy.
- Website 3 (the sepehrtherapy.ir duplicate) was deleted in milestone 6 on the
  owner's instruction; eot_main now holds website 1 only. deploy.sh checks that
  no theme view exists outside website 1.

## Reach for the gateway first - it needs no linked device
`https://eot.innerquest.me/mcp` (source: `tools/prod/mcp_server.py`, a
systemd service on eot-odoo-prod itself, `eot mcp-update` deploys it) covers
day-to-day verification with NO device link at all: `deploy_theme`,
`odoo_status`, `read_odoo_log`, `git_log`, `scss_check`, `check_site`,
`check_links`, `placeholders`, `sql_query` (read-only SELECT/WITH),
`rehearse`/`rehearse_stop`, `clone_user`, `audit` (headless Chromium, live
or `clone: true`). Runs as the unprivileged `eotmcp` user with narrow,
exact sudoers grants per tool - not a shell. Prod has 12 GB RAM (vs. the
VPS's 1 GB), so audit and rehearse run directly here, no tunnel needed.
KillMode=process on its unit matters: a plain restart would otherwise kill
any rehearsal `setsid nohup`'d from inside it (setsid escapes the session,
not the cgroup) - don't `eot mcp-update` while a rehearsal from the gateway
is still serving.

Everything below (the VPS `eot` toolkit) still exists for whatever the
gateway doesn't cover - raw shell, git history greps, backups - and for
using a linked device's browser pane. Claude reaches the VPS (95.38.234.86)
with `vps_exec`; the VPS reaches prod with `ssh eot-odoo-prod` (dedicated
key). The `eot` toolkit on the VPS (source: `tools/vps/`, install:
`tools/vps/install.sh`) returns short verdicts:

    eot deploy <ref>      deploy; on failure prints the real ParseError
    eot check [url]       page + assets + "does the CSS actually parse"
    eot placeholders      scan every sitemap page for demo placeholders + broken pages
    eot links [url]       internal links on a page that are dead (e.g. unpublished)
    eot verify [url]      run after EVERY deploy: check + links + placeholders
    eot find "text"       which view contains a string
    eot view ID | eot sql "..." | eot log | eot status | eot text URL

Added after milestone 8 (`eot help` has the full list). Reach for these
before writing an ad-hoc script:

    eot bg NAME CMD / job NAME [regex] / wait NAME / jobs
                          anything > 60 s runs detached; log + rc in /root/eot-jobs
    eot backup [LABEL]    pg_dump + filestore tgz (what rehearse restores)
    eot rehearse REF [DB] then `eot rehearse-log`   (stages + real errors only)
    eot clone-user DB     portal user on a CLONE only; creds never printed
    eot render [--clone] [--portal] [--outline N] URL...
                          status, title, tracebacks, English UI text, #wrap tree
    eot routes [--clone] [--portal]   whole sitemap + system pages, problems only
    eot audit [--clone] [--portal] [--widths ..] [all|PATH...]
                          headless Chromium running static/tools/eot_audit.js
                          (overflow, WCAG contrast, English, images, h1 font)
    eot ship REF          deploy -> verify -> routes, detached
    eot scss | eot src REGEX [addon] | eot tpl mod.xmlid [N] [GREP] | eot fa "msgid"
    eot seo test [--clone] | eot seo sweep   SEO acceptance test / sitemap-wide sweep
                          (docs/seo_runbook.md); run after library/redirect/nginx changes

VPS network (Iranian IP): files.pythonhosted.org, cdn.playwright.dev and
storage.googleapis.com are blocked; pip uses mirror-pypi.runflare.com,
Chromium comes from snap (see tools/vps/install.sh --browser). Headless
Chromium needs ~13 s to launch and ~25 s per page on 1 GB RAM: always a
background job. `--clone` audits tunnel VPS:18070 -> prod 127.0.0.1:8070.

Rules:
- Never pull big payloads (view arch, CSS, HTML, logs) into the conversation;
  grep/parse on the VPS and print only the answer.
- Don't round-trip files you already have. Edit tools in this repo, push,
  then `eot update` on the VPS.
- vps_exec calls die after ~60 s: run anything longer detached
  (`setsid nohup ... > log 2>&1 &`) and poll the log.
- Visual checks: use the desktop app's built-in browser pane
  (odoo.innerquest.me and eot.ir are allowed). Prefer JS measurements
  (computed styles, `document.styleSheets[i].cssRules.length`, element
  sizes) over many screenshots; use scaled screenshots (0.5) when needed.
  A blank screenshot right after a programmatic scroll is a capture
  artifact; wait ~1 s and re-take before concluding anything.
- Headless Chromium can't be installed on prod: cdn.playwright.dev is
  geo-blocked for Iranian IPs. The VPS has only 1 GB RAM.

## Odoo 20 pitfalls (each one bit us)
1. **No `@import url(...)` in SCSS.** The asset bundler hoists @import by
   splitting on `;`; Google Fonts URLs contain `;` → broken fragment at the
   top of the bundle → browsers drop the whole stylesheet (0 rules). Load
   webfonts with `<link>` in `views/theme_marker.xml`. `eot check` detects this.
2. **"Loads with 200" ≠ "works".** Always check the stylesheet parses
   (`eot check`) and look at the page; never report success from HTTP codes.
3. **No Font Awesome in Odoo 20** (`fa fa-*` renders 0 px), and the `oi`
   classes don't cover arbitrary glyphs. Use inline SVG icons.
4. **Specificity:** plain `.btn-primary` loses to Odoo's `.o_cc1 .btn-primary`
   etc. Scope brand overrides under `#wrapwrap`.
5. **`<template inherit_id>` needs a real external id.** Builder-made pages
   (e.g. website 1 homepage, key `website.خانه`) have none. Create the id
   in a migration (see `migrations/20.0.3.0.1/pre-migrate.py`, idempotent,
   noupdate). A `<record model="ir.model.data">` in XML only loads once and
   aborts every later upgrade ("found record of different model").
6. **Stale website-1 view copies** came over from the old instance (e.g. the
   header copy view 1601 with a t-set inside t-call). Old copies may use
   patterns Odoo 20 no longer honours; fix via theme templates, not DB edits.
7. xpath in inheritance modifies only the FIRST match; to hit every
   occurrence repeat `(//x[...])[1]` once per occurrence.
8. Language: fa_IR (RTL) is the default; a browser with English sends
   visitors to `/en` (LTR). Check both. Cookie `frontend_lang` controls it.
9. **`ir.config_parameter` has no `get_param`/`set_param` in Odoo 20.** Use
   `ICP.get_int(key, default)` / `set_int(key, val)` and
   `get_bool(key)` / `set_bool(key, val)` instead.
10. **No `request.website`.** Use `request.env.website` in controllers.
    Inside a `@staticmethod` (e.g. a sitemap generator) that only has `env`,
    there's no `request` at all — use `env.website`, never
    `env['website'].get_current_website()` (also removed).
11. **`ir.http._unslug` rejects Persian combining marks** (tashdid ّ,
    hamza ء) that `_slugify` itself produces when building the URL — Odoo
    is self-inconsistent here. Don't route through `_unslug`/`unslug`; parse
    the trailing numeric id directly: `re.search(r'(?:^|-)(\d+)$', slug)`.
    Same marks break `blog.blog.seo_name` auto-generation for `/blog/...`
    fallback URLs — set `seo_name` explicitly on affected records.
12. **Odoo's `.container` ships `::before`/`::after` clearfix pseudo-elements**
    (`display: table`, empty content). Inside a CSS Grid/Flex parent these
    become a real phantom child and eat a track/slot, silently breaking
    sidebar/TOC layouts. Diagnose with
    `getComputedStyle(el, '::before').display` (not screenshots — a wrong
    layout can look fine in a static screenshot); fix with a scoped
    `.your-scope .container::before, ::after { content: none; display: none; }`.
13. **Stored HTML content can have percent-encoded hrefs** (`%D9...`
    Persian in `href`). `unquote()` before regex-matching links against
    page content, or the match silently finds nothing.
14. **`_read_group` returns `(record, count)` tuples**, not a dict — unpack
    accordingly when counting posts/children per group.
15. **Rehearse DB-touching module changes on a disposable clone**, never
    directly on prod: `createdb` a copy (`dropdb --force` first if a prior
    clone still has idle pool connections), run the upgrade against it from
    a git worktree, serve on an unused port with `--workers=0`, curl every
    route/redirect/sitemap/edge-case, only then deploy for real. Repeat per
    round of fixes rather than patching prod directly.
16. **Sitemap is cached as `ir.attachment` rows** (`url like '/sitemap%'`).
    After changing what's in the sitemap (new redirects, filtered routes),
    delete the stale rows for the affected `website_id` only — check other
    websites' rows are untouched — so it regenerates.
17. **Repurposing `blog.blog`/`blog.post`** (extra fields + overridden
    routes/templates) is a fast way to get a full CMS content type (listing,
    detail, sitemap, RSS) without a new model — cheaper than building
    `website.page`-based custom routing from scratch, as long as the stock
    `/blog/...` routes and sitemap entries for those blogs are then
    redirected/filtered out (see #16) so they don't compete with the new
    canonical URLs.

18. **A builder page's old arch can break outside `#wrap`.** Replacing
    `#wrap` leaves the rest of the old view (e.g. `t-set`s at the top of
    `t-call="website.layout"`) in force. The old contact view called
    `request.env['website.visitor']._get_visitor_from_request()` (moved to
    `ir.http` in Odoo 20) and 500'd. Rehearse every page and xpath away
    leftovers you don't need.
19. **`odoo-bin shell` must run as the odoo user with its own HOME**:
    `sudo -u odoo env HOME=/opt/odoo ...`, never `sudo -E` (keeps root's HOME,
    so Odoo looks for the filestore under /root and attachment deletes fail).
20. **Website forms**: a hidden `email_to` input gets its security signature
    added at render time (website/models/ir_qweb.py `add_form_signature`), so
    a static recipient works. There is no outgoing mail server on eot_main
    yet: submissions are stored as `mail.mail` in state "exception" until one
    is configured.
21. **The prod service's cron touches every database on the server**, including
    a rehearsal clone (harmless version-mismatch tracebacks in the log). Drop
    the clone as soon as the rehearsal is done.
22. **Redirect a URL that is still a page with a controller route**, not a
    `website.rewrite`: Odoo serves an existing page before it looks at
    redirect records (controllers/redirects.py).

23. **No `filter` / `backdrop-filter` / `transform` on `#top`.** Any of
    them makes the header the containing block of Odoo's *fixed* mobile
    offcanvas menu: the closed menu widened every page on phones
    (702px scroll width in a 375px viewport) and would open trapped inside
    the header (milestone 8).
24. **`#wrap .container::before { display: table }` is ID-scoped.** A
    class-scoped reset (`.eot-pg .container::before`) loses to it, so the
    phantom grid item from #12 comes back. Anchor resets on `#wrapwrap`
    (see the top of the homepage section in theme.scss).
25. **Check class names across all three stylesheets before adding one.**
    theme.scss's first `.eot-dot` collided with library.scss's glossary
    separator. Theme-wide atoms now use distinct names (`.eot-pdot`).
26. **Site-wide heading colour vs. dark surfaces.** `h1..h6` get the ink
    colour globally; headings inside teal/dark surfaces must `color:
    inherit` (pages.scss does this for .eot-hero, dark cards, bands).
27. **Untranslated core UI strings**: literal template text, t-call
    attribute strings (`additional_title`, `title=`), Python `_()` strings
    and portal.entry record names have no fa.po entry upstream for many
    portal/auth screens. Patch templates in views/i18n.xml (copy the element
    from the Odoo 20 source on eot-odoo-prod, change only the wording) and
    record names in a migration (fa_IR key only). An xpath replaces only its
    FIRST match - match on exact class/text, never a shared attribute
    (`data-bs-dismiss` hit a modal's close button first).
28. **`website.layout` builds `<title>` from `additional_title`**, falling
    back to the main object's/view's name ("Login", "My Portal"). Set
    `additional_title` in Persian for system pages.

29. **Odoo 20 only honours proxy headers when `X-Forwarded-Host` is sent**
    (`odoo/http/router.py`: ProxyFix runs only if HTTP_X_FORWARDED_HOST is
    present). nginx sent only X-Forwarded-Proto, so the sitemap and
    robots.txt said `http://`. Both vhosts now send it (SEO milestone).
30. **Record ids from the old site were reused.** `/blog/<name>-<id>` URLs
    from the old DB point at ids that now belong to other books/posts, and
    werkzeug "fixes" the slug by redirecting to whatever owns the id. Never
    write redirect targets with ids from another database; match by title
    (`models/fa_text.py fa_match_key`). The guard is `models/seo.py`
    `IrHttpSeo._match`. `website.rewrite` rules only apply when NO route
    matched (`_serve_fallback`).
31. **Anything raised in `ir.http._match` before `super()`** skips
    http_routing's language setup: the 404 fallback then dies with
    `'Request' object has no attribute 'lang'` (500). Call super first.
32. **QWeb `t-out` HTML-escapes a plain str.** JSON-LD passed as
    `structured_data` must be `Markup`, made script-safe first
    (`<`, `>`, `&` as \u escapes) - see `controllers/seo_jsonld.render`.
33. **Odoo 20 caches anonymous `website.page` HTML** (website_page.py
    `_get_response`, 1 h) keyed by website/lang/path only - not host, not
    bot. The `<head>` depends on the host (noindex when it isn't the website
    domain), so one visit to odoo.innerquest.me (or a 127.0.0.1 probe) put
    `noindex` on the live homepage. The theme adds host root + bot flag to
    the key (`models/seo.py WebsitePageSeo`). When a page differs between
    `/` and `/?x=1`, suspect this cache (query strings bypass it).

## Verifying a design deploy
1. `eot rehearse origin/<branch> eot_mNtest` -> `eot rehearse-log`
2. `eot routes --clone`; `eot clone-user eot_mNtest`; `eot routes --clone --portal`
3. `eot audit --clone --portal all` (background; `eot job audit`)
4. `eot rehearse-stop eot_mNtest`, then `eot ship origin/<branch>` and
   `eot audit all` against live.
- Audit from the DOM (static/tools/eot_audit.js), not screenshots:
  scrollWidth, every text node's WCAG contrast against its real background,
  English text, broken images, heading fonts. Screenshots after a
  programmatic scroll are often stale. The browser pane is for looking at a
  design, not for bulk checks; if needed there,
  `await import('/theme_eot_custom/static/tools/eot_audit.js')` and use
  `eotAudit.start(paths, 375)` / `eotAudit.report()`.
- Never create or sign in to accounts on the live DB; signed-in checks run
  on the clone only (eot refuses eot_main*).

## Tools added in milestone 6
    scripts/rehearse.sh [ref] [db] [cleanup-script]
                                  restore the latest backup into a scratch DB,
                                  upgrade from a worktree, optionally dry-run
                                  then run a cleanup script, serve on :8070.
                                  Generalized after milestone 6 (was hardcoded
                                  to eot_m6test/m6_cleanup.py) - reuse it as-is
                                  for future milestones, don't fork a copy.
    scripts/gen_catalogs.py       regenerate views/pages_catalog.xml from
                                  data/m6_catalog_source.json
    scripts/m6_cleanup.py         one-off milestone-6 cleanup (website 3 +
                                  stub deletion); kept as the template for a
                                  future milestone's own cleanup script - copy
                                  its assert-preconditions/dry-run/abort-loud
                                  shape rather than writing one from scratch.

## Patterns worth reusing (not just eot-specific)
- **Assert preconditions, then act; abort loud on mismatch.** Before any
  irreversible DB change, check the thing you're about to delete/change is
  actually what you think it is (id, name, domain, url prefix...) and raise
  rather than proceeding on a wrong guess. See `scripts/m6_cleanup.py`.
- **Dry-run flag before the real run**, printing the same report either way,
  so the diff is visible before it's committed (`EOT_DRY_RUN=1`).
- **Long vps_exec/shell jobs: fire detached, poll the log.** Don't block a
  60s-capped call on a multi-minute job (`setsid nohup ... > log 2>&1 &`,
  poll with `tail`/`grep`).
- **Long-running browser-side JS: fire-and-poll, not one blocking call.**
  Store progress on a global (`window.__x`), return immediately, poll with
  short follow-up calls - avoids the tool's own timeout on async work that
  outlives it.
- **Large structured data leaving the VPS: gzip+base64, not raw paste**,
  with an MD5 check on both ends, and cross-validate counts against the
  source's own displayed totals before trusting the extract.

- **`pkill -f` / `pgrep -f` over ssh match their own command line.** The
  pattern text is inside `bash -c '...'`, so `pkill -f "d eot_m7test"`
  killed its own ssh shell and silently skipped the dropdb after it. Use a
  bracket pattern (`pkill -f "[-]d eot_m7test"`) and confirm the result
  (e.g. list `pg_database`) instead of trusting a missing echo.

- **A second ad-hoc script for the same check means it should be an `eot`
  command.** Milestone 8 rewrote route sweeps, signed-in renders, source
  greps and the browser audit several times each; they are now tools.
- **Python piped over ssh buffers stdout**: a polled job's log stays empty
  until the end. Run the remote interpreter with `-u`.
- **Push with an explicit `origin <branch>`** and read the ref line; a bare
  `git push` without upstream failed silently and the VPS tested a stale
  commit. Branch from `origin/main`, not a possibly stale local `main`.
- **Check `<title>` too**: tab titles fall back to the view name in English
  (`additional_title`, #28); body-text scans don't see them. `eot routes`
  flags them.

## Owner's standing rules
- No placeholders anywhere on the site (demo phones, yourcompany emails,
  lorem ipsum...). Remove them; real values are added deliberately later.
  Run `eot placeholders` after every deploy.
- Check the result yourself; don't ask the owner to test on their phone.
- Milestone flow: mockup → approval → branch → deploy → verify → merge to main.
