# theme_eot_custom

Custom Odoo 20 website theme for **eot.ir** (هیجان اندیشه).

The repository root *is* the addon. It is cloned on the server as
`/opt/odoo/themes/theme_eot_custom`, which is already on `addons_path`.

## Scope: website_id 1 only

The database (`eot_main`) holds two websites:

| id | website | touched by this module? |
|----|---------|-------------------------|
| 1  | eot.ir (هیجان اندیشه) | **yes** |
| 3  | sepehrtherapy.ir (duplicate copy) | **never** |

Scoping comes from Odoo's own theme mechanism, not from hand-set `website_id`s:

* Because the module name starts with `theme_`, every `<template>` in `views/`
  is stored as a `theme.ir.ui.view` *template*, not a live view. Odoo copies it
  into a real `ir.ui.view` with `website_id` set, and only for websites whose
  `theme_id` is this module. Website 1 is the only one.
* When the target view already has a website-1-specific copy (e.g. the header
  or footer templates customised in the editor), the copied view inherits from
  that copy automatically.
* Manifest `assets` of a `theme_*` module are only included in the bundles of
  websites whose `theme_id` is this module (`website/models/ir_asset.py`,
  `_get_active_addons_list`).

**Rule for all future work:** anything visual goes in `views/` as
`<template inherit_id="..."><xpath .../></template>` or in `static/src/scss/`.
No `<record model="ir.ui.view">`, no `ir.asset` records, no sweeping
`position="replace"` of whole layouts, and no page/menu data that is not
explicitly for website 1.

## First install (one time only)

Done once to bind the theme to website 1 without touching website 3 and
without the UI theme switcher's reset of editor customisations:

```sh
cd /opt/odoo/themes
git clone git@github-theme-eot-custom:akazemilab/theme_eot_custom.git
# register the new module, then point website 1 at it
sudo -u odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin shell \
    -c /etc/odoo20.conf -d eot_main --no-http <<'PY'
env['ir.module.module'].update_list()
env['website'].browse(1).theme_id = env['ir.module.module'].search([('name', '=', 'theme_eot_custom')])
env.cr.commit()
PY
systemctl stop odoo20
sudo -u odoo /opt/odoo/venv/bin/python3 /opt/odoo/odoo/odoo-bin \
    -c /etc/odoo20.conf -d eot_main -i theme_eot_custom --stop-after-init --no-http
systemctl start odoo20
```

Installing with website 1's `theme_id` already set makes Odoo copy the theme
templates to website 1 only (`ir_module_module.write` ->
`_theme_get_stream_website_ids` -> `_theme_load`).

## Deploying

Run on the server as root (see `scripts/deploy.sh`):

```sh
/opt/odoo/themes/theme_eot_custom/scripts/deploy.sh <branch-or-commit>
```

It fetches, checks out the ref, runs
`odoo-bin -c /etc/odoo20.conf -d eot_main -u theme_eot_custom --stop-after-init`,
restarts `odoo20`, and prints the log lines produced during the upgrade.

Check the result at <http://odoo.innerquest.me/> (serves website 1).

## Rolling back a milestone

```sh
/opt/odoo/themes/theme_eot_custom/scripts/deploy.sh <previous-good-commit>
```

Upgrading to an older commit re-syncs the website-1 views from the templates
in that commit: views that no longer exist in the module are removed, changed
ones are rewritten.

**Do not** use *Website → Themes → Remove* / *Choose another theme* in the UI
for rollback. That path calls `theme.utils._reset_default_config()`, which
resets website 1's font, palette, header-template and footer-template
customisations in `user_values.scss`. Initial activation was done by setting
`website.theme_id` directly and installing from the CLI to avoid that reset.

## Branching

* `main` - what is approved.
* `milestone/NN-name` - one branch per milestone; deployed to the server for
  review, merged into `main` only after approval.
