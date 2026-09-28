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

## Token efficiency: do the heavy work on the VPS
Claude reaches the VPS (95.38.234.86) with `vps_exec`; the VPS reaches prod
with `ssh eot-odoo-prod` (dedicated key). The `eot` toolkit on the VPS
(source: `tools/vps/`, install: `tools/vps/install.sh`) returns short verdicts:

    eot deploy <ref>      deploy; on failure prints the real ParseError
    eot check [url]       page + assets + "does the CSS actually parse"
    eot placeholders      scan every sitemap page for demo placeholders + broken pages
    eot links [url]       internal links on a page that are dead (e.g. unpublished)
    eot verify [url]      run after EVERY deploy: check + links + placeholders
    eot find "text"       which view contains a string
    eot view ID | eot sql "..." | eot log | eot status | eot text URL

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

## Tools added in milestone 6
    scripts/rehearse.sh [ref]     restore the latest backup into eot_m6test, upgrade
                                  from a worktree, run the cleanup, serve on :8070
    scripts/gen_catalogs.py       regenerate views/pages_catalog.xml from
                                  data/m6_catalog_source.json

## Owner's standing rules
- No placeholders anywhere on the site (demo phones, yourcompany emails,
  lorem ipsum...). Remove them; real values are added deliberately later.
  Run `eot placeholders` after every deploy.
- Check the result yourself; don't ask the owner to test on their phone.
- Milestone flow: mockup → approval → branch → deploy → verify → merge to main.
