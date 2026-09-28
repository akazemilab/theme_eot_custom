# Milestone 6 one-off cleanup of eot_main. Owner's instruction (2026-09-28):
# "don't keep any unpublished page and delete sepehrtherapy related pages
# all ... clean it up entirely".
#
# Run AFTER the 20.0.6.0.0 theme deploy (it relies on the page ids that
# deploy creates, and refuses to run without them), through odoo shell:
#
#   sudo -u odoo env HOME=/opt/odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell \
#       -c /etc/odoo20.conf -d eot_main --no-http < scripts/m6_cleanup.py
#
# Set EOT_DRY_RUN=1 to report without changing anything.
#
# What it removes:
#   1. website 3 ("سپهر هیجان اندیش", the sepehrtherapy.ir duplicate copied
#      in with the database). sepehrtherapy.ir itself lives on another
#      server and is not served from here; its DNS never pointed here.
#   2. website-1 pages left unpublished that are not one of the milestone-6
#      pages: the pre-library stubs (/کتب/*, /مقالات,
#      /فرهنگنامه/روانشناسی-تعاملی). Controller routes own those URLs.
#   3. generic pages that are dead: /courses/* (errored in Odoo 20),
#      helpdesk/project confirmation pages (modules not installed), the
#      demo /my/psychological-results page (module not installed). Their
#      URLs 301 via controllers/redirects.py.
#   4. unpublishes the stock /privacy stub (it 301s to /حریم-خصوصی).
#   5. drops website 1's cached sitemap so it regenerates.
import os

DRY = os.environ.get("EOT_DRY_RUN") == "1"
say = print

ours = env["ir.model.data"].search([("module", "=", "theme_eot_custom"), ("name", "=like", "eot\\_pv\\_%")])
if len(ours) != 19:
    raise SystemExit("ABORT: expected 19 theme_eot_custom.eot_pv_* ids, found %d - deploy 20.0.6.0.0 first" % len(ours))
our_view_ids = set(ours.mapped("res_id"))
Page = env["website.page"].with_context(active_test=False)

# 1. website 3 --------------------------------------------------------------
w3 = env["website"].browse(3).exists()
if w3:
    if "sepehr" not in (w3.domain or "") and "سپهر" not in (w3.name or ""):
        raise SystemExit("ABORT: website 3 is not the sepehrtherapy duplicate: %r %r" % (w3.name, w3.domain))
    n_pages = Page.search_count([("website_id", "=", 3)])
    n_views = env["ir.ui.view"].with_context(active_test=False).search_count([("website_id", "=", 3)])
    n_menus = env["website.menu"].search_count([("website_id", "=", 3)])
    n_att = env["ir.attachment"].search_count([("website_id", "=", 3)])
    say("website 3 %r: %d pages, %d views, %d menus, %d attachments -> delete" % (w3.name, n_pages, n_views, n_menus, n_att))
    if not DRY:
        env["ir.attachment"].search([("website_id", "=", 3)]).unlink()
        w3.unlink()
else:
    say("website 3: already gone")

# 2. unpublished website-1 stubs -------------------------------------------
ALLOWED_PREFIXES = ("/کتب", "/مقالات", "/فرهنگنامه/روانشناسی-تعاملی")
stubs = Page.search([("website_id", "=", 1), ("is_published", "=", False)])
stubs = stubs.filtered(lambda p: p.view_id.id not in our_view_ids)
bad = stubs.filtered(lambda p: not p.url.startswith(ALLOWED_PREFIXES))
if bad:
    raise SystemExit("ABORT: unexpected unpublished page(s), not touching them: %s" % bad.mapped("url"))
say("website 1 unpublished stubs: %d -> delete" % len(stubs))
if not DRY:
    stubs.unlink()

# 3. dead generic pages ----------------------------------------------------
DEAD = ["/courses/alnafs", "/courses/commission", "/courses/masnavi", "/courses/parenting",
        "/courses/peyvand", "/your-ticket-has-been-submitted", "/your-task-has-been-submitted",
        "/my/psychological-results"]
dead = Page.search([("website_id", "=", False), ("url", "in", DEAD)])
owned = env["ir.model.data"].search([("model", "=", "ir.ui.view"), ("res_id", "in", dead.mapped("view_id").ids)])
if owned:
    raise SystemExit("ABORT: dead pages have module-owned views: %s" % owned.mapped("complete_name"))
say("generic dead pages: %d -> delete (%s)" % (len(dead), ", ".join(dead.mapped("url"))))
if not DRY:
    views = dead.mapped("view_id")
    dead.unlink()
    views.exists().unlink()

# 4. stock /privacy stub ---------------------------------------------------
priv = Page.search([("website_id", "=", False), ("url", "=", "/privacy"), ("is_published", "=", True)])
say("stock /privacy: %d -> unpublish" % len(priv))
if not DRY:
    priv.write({"is_published": False})

# 5. sitemap cache ---------------------------------------------------------
sm = env["ir.attachment"].search([("url", "=like", "/sitemap%"), ("website_id", "=", 1)])
say("website 1 sitemap cache rows: %d -> delete" % len(sm))
if not DRY:
    sm.unlink()

left = Page.search([("website_id", "in", [1, False]), ("is_published", "=", False)])
say("unpublished pages left (website 1 + generic): %s" % (left.mapped("url") or "none"))
if DRY:
    env.cr.rollback()
    say("DRY RUN - rolled back")
else:
    env.cr.commit()
    say("DONE - committed")
