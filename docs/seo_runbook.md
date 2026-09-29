# eot.ir SEO runbook

Baseline and findings: `docs/seo_audit_2026-09-29.md`. Fixes shipped in milestone 9
(`seo/m9`, theme 20.0.9.0.0) plus an nginx change on eot-odoo-prod (below).

## Re-run the checks

| What | Command (on the VPS) | Output |
|---|---|---|
| Acceptance test (robots, sitemap, per-template tags + JSON-LD, 20 redirect cases) | `eot seo test` then `eot job seo-test` | ok/FAIL lines, `RESULT: N failures` |
| Same against a rehearsal clone | `eot rehearse origin/<branch> eot_xtest` → `eot seo test --clone` | same |
| Every sitemap URL | `eot seo sweep` then `eot job seo-sweep` (~5 min) | per-section verdicts; rows in `/root/eot-jobs/seo_sweep.tsv` |
| Design/English/overflow | `eot audit all` / gateway `audit` | unchanged tools |

Run `eot seo test` after every deploy that touches the library, redirects, `views/seo.xml`,
`models/seo.py`, or nginx. Add a case to `tools/vps/eotseo_test.py` for any new redirect.

## What is where

- **nginx** (`/etc/nginx/sites-available/eot-odoo`, `talentsearch.conf`): `proxy_set_header
  X-Forwarded-Host $host;` next to `X-Forwarded-Proto`. Without it Odoo 20 ignores the proxy
  headers (`odoo/http/router.py`, ProxyFix only runs when X-Forwarded-Host is present) and
  builds `http://` URLs in the sitemap and robots.txt. Backups of the pre-change files:
  `/root/nginx-backup-*.20260929-*` on prod.
- **Redirect map**: `website.rewrite` rows of website 1. Rebuilt by title in
  `migrations/20.0.9.0.0/post-migrate.py`. Rewrites only apply when no route matched.
- **Reused-id guard**: `models/seo.py` `IrHttpSeo._match` — a `/blog/...` URL whose name
  does not match the record behind its id goes to the library item with that name, or 404.
- **JSON-LD**: `controllers/seo_jsonld.py` (library pages), `models/seo.py` (Organization,
  WebSite on the homepage).
- **Share image / descriptions**: `models/seo.py` (`_default_website_meta` for library
  blogs/posts, falls back to the website's Default Social Share Image, else the logo);
  `/کتب` description via `eot_meta_description` (`views/seo.xml`).
- **Slugs**: `models/fa_text.py` `fa_slug_text()`; old slugs 301 by trailing id.

## Search Console (property `sc-domain:eot.ir`)

UI-only actions (the API tools are read-only): submit sitemap, Validate fix, Request
indexing (quota ~10/day; only final, high-value URLs), Removals (owner's yes only).
Sitemap to submit: `https://www.eot.ir/sitemap.xml` (single urlset, ~1,040 URLs).

## Measurement plan (query_search_analytics, property sc-domain:eot.ir)

Baseline, 2026-07-15 → 2026-09-27: 25–50 impressions/day, 1–9 clicks/day, almost only the
homepage; library URLs "unknown to Google". Expect nothing in the first days: discovery and
indexing are Google's decision and usually take days to weeks.

| When | Check | Healthy sign |
|---|---|---|
| +1 week | Sitemaps report: status Success, discovered ≈ sitemap count | no fetch errors |
| +2 weeks | `inspect_url` on 10 library URLs (2 books, 3 chapters, 3 articles, 2 terms) | "Submitted and indexed" or "Crawled"; Google canonical = ours |
| +2 / +4 / +8 weeks | `query_search_analytics` by page, 28-day window | pages under `/کتب/`, `/مقالات/`, `/فرهنگنامه/` appear with impressions |
| +4 / +8 weeks | by query: انتظار، پارادایم، هوش تعاملی، حمایت معنوی، سرسختی شناختی، روانشناسی فرهنگی | impressions return; position ≤ 10 for the ones with a live page |
| +8 weeks | daily impressions vs baseline | sustained rise above ~50/day |
| +8 weeks | Page indexing report | "Page with redirect" / "Not found (404)" for old URLs is expected, not an error |

Old-era striking-distance queries whose pages no longer exist (گلوبالیسم، هویت فردی، تصور و
مفهوم، نگهداری ذهنی، آگاهی و اراده) will not come back unless that content is republished.
