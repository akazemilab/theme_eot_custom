# EOT article routine (compact runbook)

Input: the owner attaches .docx articles in the claude.ai Project "Eot.ir" chat.
Output: drafts in blog 46 «مقالات» (author partner 7, the founder), published on approval.
Every number below was verified on 2026-10-14 (batch of 14, posts 2021-2034).

## 1. Prepare (sandbox, one script run - never rewrite text by hand)
`tools/articles/eot_article_prep.py` (usage in its docstring):
pandoc docx -> html, then the script normalises Persian typography only
(ي/ك -> ی/ک except in words with harakat, Arabic digits -> Persian, spacing
around ، ؛ ؟, ZWNJ for می/نمی/ها/های, a small fixed word list), strips
images/inline styles/spans, keeps `fn*` ids so footnotes work, normalises the
outline to start at h2 with no skipped levels, and links up to 5 glossary
terms (longest first, one per paragraph, never headings, a GENERIC stoplist).
It proves `canon(text before) == canon(text after)`; every row must print
`text-unchanged=True`.
Fields: name = eot_title = title; eot_excerpt = teaser_manual = first 120-160
chars of real text (no footnote numbers); eot_words; eot_minutes =
max(1, ceil(words/200)); eot_topic from topics.json; eot_ltr = 0.
URL is /مقالات/<fa_slug(eot_title)>-<id>; seo_name stays empty.

## 2. Import
The owner imports `articles.csv` in Odoo (blog.post import, Persian UI), or
create via odoo_execute. Verify the import by comparing md5 of content
against out/aNN.json (SQL), not by reading the HTML.

## 3. Publish + verify
odoo_execute write is_published=true (the MCP user has Website Restricted
Editor). Then check_site on the new paths (title, one h1, canonical, JSON-LD
Article with author Person, wordCount, datePublished for posts created
after 2026-09-26), check_links, and the sitemap. Old URLs: website_rewrite
rows with redirect_type 404 whose slug matches a new title -> switch to 301.

## 4. Things that are dynamic now (don't hard-code)
Home page hero stat, home "N مقاله منتشرشده" heading, the home latest-6
list, and the founder page card all use BlogPost.eot_article_count() /
eot_latest_articles(). The books count (۲۰) is still literal.

## Deploy / gateway rules learnt the hard way
- The tools server pushes to GitHub with the deploy key alias
  `github-eot-theme` (push URL already set). Ship = merge to main, push,
  `deploy_theme(ref=main)`. Keep main == what is deployed.
- `deploy_theme` has NO dry run. Since b04ecbc the gateway refuses any
  argument a tool does not declare (before that, a `dry_run` flag was
  silently ignored and the deploy went live).
- `rehearse` runs detached: if it answers "still running", call it again with
  the same ref and db. Use `origin/<branch>` as ref (plain `main` resolves to
  a stale local branch in the prod checkout). Always `rehearse_stop` after.
- The proxy in front of the gateway cuts any request at 60s.
- A theme upgrade does not overwrite a website view whose arch_updated is
  true (view 1651 page_founder was one). Check live HTML after every deploy;
  fix by ir.ui.view write of arch_db.
- `odoo_replace_text` is text-only (no < > &); structural edits go in the theme.

## Token rules
Read attachments once; scripts do the work; SQL for lookups (never crawl);
report in about 5 lines.
