#!/usr/bin/env python3
"""Print the source of one core Odoo template/record from the Odoo 20 tree
on eot-odoo-prod, so an i18n.xml / inheritance patch can copy the exact
element instead of guessing (CLAUDE.md pitfall #27).

  tpl.py module.xmlid [MAXLINES] [GREP]

Looks in odoo/addons/<module> and enterprise/<module>; prints
"file:line" then the element (template/record/menuitem) up to its closing
tag, capped at MAXLINES (default 60). With GREP, prints only the lines of
that element matching the regex (with line numbers) - use it to find the
exact node to xpath on without pulling the whole template.
"""
import glob
import re
import sys

if len(sys.argv) < 2 or "." not in sys.argv[1]:
    sys.exit("usage: tpl.py module.xmlid [maxlines] [grep]")
module, xid = sys.argv[1].split(".", 1)
cap = int(sys.argv[2]) if len(sys.argv) > 2 else 60
pat = re.compile(sys.argv[3]) if len(sys.argv) > 3 else None

roots = ["/opt/odoo/odoo/addons/%s" % module, "/opt/odoo/enterprise/%s" % module,
         "/opt/odoo/odoo/odoo/addons/%s" % module]
opener = re.compile(r'<(template|record|menuitem)\b[^>]*\bid="%s"' % re.escape(xid))
found = 0
for root in roots:
    for f in sorted(glob.glob(root + "/**/*.xml", recursive=True)):
        lines = open(f, encoding="utf-8").read().split("\n")
        for i, line in enumerate(lines):
            m = opener.search(line)
            if not m:
                continue
            found += 1
            tag = m.group(1)
            end = i
            if not re.search(r"/>\s*$", line) or tag != "menuitem":
                depth = 0
                for j in range(i, len(lines)):
                    depth += len(re.findall(r"<%s\b" % tag, lines[j])) - len(re.findall(r"</%s>" % tag, lines[j]))
                    if re.search(r"<%s\b[^>]*/>" % tag, lines[j]):
                        depth -= 1
                    if depth <= 0:
                        end = j
                        break
            block = lines[i:end + 1]
            print("%s:%d  (%d lines)" % (f.replace("/opt/odoo/", ""), i + 1, len(block)))
            if pat:
                for k, bl in enumerate(block):
                    if pat.search(bl):
                        print("%5d  %s" % (i + 1 + k, bl.strip()[:200]))
            else:
                print("\n".join(block[:cap]))
                if len(block) > cap:
                    print("... (%d more lines; pass a larger MAXLINES or a GREP)" % (len(block) - cap))
if not found:
    sys.exit("!! %s.%s not found under %s" % (module, xid, ", ".join(roots)))
