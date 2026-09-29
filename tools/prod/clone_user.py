# Runs inside `odoo-bin shell -d <clone>` (fed on stdin by `eot clone-user`).
# Creates or resets a portal user on a DISPOSABLE REHEARSAL CLONE only, so
# account pages (/my, /my/addresses, /my/security ...) can be rendered and
# audited signed in. Never run against eot_main: accounts are never created
# on the live database. The eot wrapper refuses eot_main* before calling this,
# and this script re-checks the database name itself.
#
# Prints exactly two machine-readable lines (the wrapper stores them in a
# root-only file on the VPS and never echoes the password):
#   EOT_CLONE_LOGIN=...
#   EOT_CLONE_PASSWORD=...
import secrets

db = env.cr.dbname  # noqa: F821  (env is provided by odoo shell)
if db == "eot_main" or db.startswith("eot_main_") or not db.startswith("eot_"):
    raise SystemExit("!! refusing: %r is not a rehearsal clone" % db)

LOGIN = "eot-audit@rehearsal.invalid"
pw = secrets.token_urlsafe(18)
Users = env["res.users"].sudo().with_context(no_reset_password=True, active_test=False)  # noqa: F821
portal = env.ref("base.group_portal")  # noqa: F821
gfield = "group_ids" if "group_ids" in Users._fields else "groups_id"

user = Users.search([("login", "=", LOGIN)], limit=1)
if not user:
    user = Users.create({
        "name": "حساب آزمایشی",
        "login": LOGIN,
        "email": LOGIN,
        "lang": "fa_IR",
        gfield: [(6, 0, [portal.id])],
    })
user.write({"password": pw, "active": True})
env.cr.commit()  # noqa: F821
print("EOT_CLONE_LOGIN=" + LOGIN)
print("EOT_CLONE_PASSWORD=" + pw)
