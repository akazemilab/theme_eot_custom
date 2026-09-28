# Next milestone: redesign the remaining eot.ir pages

Ready-to-paste prompt for a future session, modeled on the Books/Articles/
Glossary milestone (mockup on real data → approval → build → deploy →
verify → merge). Page inventory below was pulled live from `eot_main` via
`eot sql` against `website_page`/`website_menu` on 2026-09-28 — re-check it
before starting, content may have changed.

---

## Prompt

Design a visual refresh for eot.ir's remaining static/informational pages
(everything outside the Books/Articles/Glossary library already shipped).
Follow the same process as that milestone: pull the real, current content
for each page from the live `eot_main` database with `eot sql`/`eot text`,
mockup every page on a Design Artifact canvas using that real content (no
lorem ipsum, no placeholder names/numbers), then wait for approval before
touching code. Stay inside the existing eot.ir brand (teal/sand/paper
palette, Vazirmatn body / Estedad headings), RTL-first Persian only
(check the `/en` LTR variant too), inline SVG icons only — there is no
Font Awesome in Odoo 20 here. Read `CLAUDE.md` in theme_eot_custom first;
it has the deploy mechanics and a running list of Odoo-20-specific
pitfalls (`.container` clearfix-in-grid, `_unslug` rejecting Persian
marks, `ir.config_parameter` API, sitemap caching, etc.) hit while
building the library pages — assume the same class of bugs is waiting
here too.

### Page groups to design (18 pages, grouped by function — treat each
group as one visual system, the way Books/Articles/Glossary each got
their own identity)

**1. Services & offerings** — the commercial core, should look the most
"product-page" polished:
- `/خدمات` — خدمات هیجان اندیشه (services overview/hub)
- `/مشاوره-روانشناسی-آنلاین` — online counseling
- `/کلاس-گروهی-آنلاین` — group classes
- `/کارورزی-روانشناسی-آنلاین` — online internship/practicum
- `/یادگیری-خودیار-روانشناسی` — self-directed learning center
- `/آزمون-روانشناسی` — psychological tests & assessments

**2. Trust & methodology** — long-form, credibility-building, should read
calmer/more editorial than the services pages:
- `/دکتر-ناصرالدین-کاظمی-حقیقی` — founder bio
- `/اصول-علمی-و-تحریریه` — scientific & editorial principles
- `/ایمنی-روانشناختی` — psychological safety policy
- `/روش-ارزیابی-و-تفسیر` — assessment & interpretation methodology
- `/راهنمای-سایت` — site guide
- `/سوالات-متداول` — FAQ

**3. Legal/policy** — one shared minimal template is fine here, these
don't need distinct identities:
- `/حریم-خصوصی` (+ stock `/privacy`, check which is canonical)
- `/سیاست-کوکی` — cookie policy
- `/شرایط-استفاده` — terms of use
- `/دسترس-پذیری` — accessibility statement

### Known problems to fix as part of this milestone, not just redesign

- `/contactus` and `/about` are unpublished stock Odoo pages, 404ing —
  `eot links https://www.eot.ir/` currently flags both as broken links
  from the homepage. Either publish real content or repoint the homepage
  links.
- `/courses/alnafs`, `/courses/commission`, `/courses/masnavi`,
  `/courses/parenting`, `/courses/peyvand` (5 pages) 500-error — old
  builder page(s) calling `ir.config_parameter.get_param`, which doesn't
  exist in Odoo 20 (same class of bug documented in CLAUDE.md #9, just in
  inherited/pre-existing content this time, not new code). Confirm with
  `eot log` and decide whether these get folded into this milestone's
  scope or handled separately — they're currently live-broken regardless.
- Leftover **unpublished duplicate builder pages** from before the
  library migration are still in `website_page` and should be deleted,
  not redesigned, since the new controller routes already own these
  URLs: all `/کتب/*` stub pages, `/مقالات`, and
  `/فرهنگنامه/روانشناسی-تعاملی`. Verify each is genuinely superseded
  (`is_published = f`, no incoming links) before deleting.
- `/contactus-thank-you`, `/your-task-has-been-submitted`,
  `/your-ticket-has-been-submitted` are transactional confirmation pages —
  low design priority, but worth a pass so they match brand once the
  pages that lead into them are redesigned.

### Process reminders from the last milestone

- Gather real content first (`eot sql`, `eot text URL`) — never open a
  skill/artifact type before the material is in hand.
- Mockup on a Design Artifact canvas, present per-group, and this time
  make your own calls on any data-quality gaps the way the last
  milestone was told to (ask only if a decision is genuinely destructive
  or ambiguous in a way the owner would care about).
- Build in a git worktree, rehearse against a disposable DB clone
  (`createdb`/`dropdb --force`, module upgrade, curl every route) before
  ever touching prod.
- Deploy via `eot deploy <ref>`, then always `eot verify` (check + links +
  placeholders) immediately — this site is live, there is no staging.
- `eot placeholders` must come back clean and `website 3`
  (sepehrtherapy duplicate) must be untouched before merging to `main`.

---

*Generated after the Books/Articles/Glossary milestone
(merge commit `7b46ef6`) as the requested follow-up prompt. Page list and
known-issue list reflect a live DB snapshot taken 2026-09-28 — reverify
before use, especially the `/courses/*` and unpublished-duplicate items.*
