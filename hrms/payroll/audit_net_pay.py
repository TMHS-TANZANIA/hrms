"""Which salary slips would pay a different amount if recomputed against today's structure?

	cd sites
	../env/bin/python ../apps/hrms/hrms/payroll/audit_net_pay.py <site> [payroll entry]
	../env/bin/python ../apps/hrms/hrms/payroll/audit_net_pay.py <site> [payroll entry] --apply

Without --apply nothing is written: each slip is recomputed on a copy and rolled back.

With --apply, DRAFT slips are re-saved, which rebuilds every component row from the
current Salary Structure. A submitted Payroll Entry does not block this - the slips are
what carry the money, and a draft slip is still editable under an approved entry.
Submitted slips are only reported; those need cancel and amend.
"""

import sys

import frappe
from frappe.utils import flt

apply_fix = "--apply" in sys.argv
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if not args:
	print(__doc__)
	raise SystemExit(1)

frappe.init(site=args[0])
frappe.connect()
frappe.set_user("Administrator")

filters = {"docstatus": ("!=", 2)}
if len(args) > 1:
	filters["payroll_entry"] = args[1]

fixed = stuck = skipped = 0
total = 0.0

for s in frappe.get_all(
	"Salary Slip", filters=filters,
	fields=["name", "employee_name", "payroll_entry", "docstatus", "net_pay"], order_by="name"
):
	before = flt(s.net_pay)
	was = {r.salary_component for r in frappe.get_doc("Salary Slip", s.name).deductions}

	try:
		if apply_fix and s.docstatus == 0:
			doc = frappe.get_doc("Salary Slip", s.name)
			doc.save()
		else:
			doc = frappe.copy_doc(frappe.get_doc("Salary Slip", s.name))
			doc.docstatus = 0
			doc.get_emp_and_working_day_details()
			doc.calculate_net_pay()
	except Exception as e:
		skipped += 1
		print("  ?? %-32s %s  (%s)" % (s.employee_name, s.name, str(e)[:60]))
		continue

	diff = before - flt(doc.net_pay)
	if abs(diff) <= 0.5:
		continue

	total += diff
	added = {r.salary_component for r in doc.deductions} - was
	state = "FIXED  " if (apply_fix and s.docstatus == 0) else "DRAFT  " if s.docstatus == 0 else "SUBMITTED"
	if s.docstatus == 0:
		fixed += 1
	else:
		stuck += 1
	print("  %s %-32s %s" % (state, s.employee_name, s.name))
	print("       entry=%s  was %.2f  now %.2f  differs by %.2f"
	      % (s.payroll_entry, before, flt(doc.net_pay), diff))
	if added:
		print("       deductions added: %s" % ", ".join(sorted(added)))

if apply_fix:
	frappe.db.commit()
	print("\nre-saved draft slips: %d   still needing cancel+amend (submitted): %d" % (fixed, stuck))
else:
	frappe.db.rollback()
	print("\ndraft slips fixable by --apply: %d   submitted (cancel+amend): %d" % (fixed, stuck))
print("net difference: %.2f   unrecomputable: %d" % (total, skipped))
