"""Pre-flight: does this site's payroll wiring silently evaluate a formula to zero?

	cd sites
	../env/bin/python ../apps/hrms/hrms/payroll/audit_salary_setup.py <site>

Read-only. Nothing is written.

Salary Slip pre-seeds EVERY salary component abbreviation to 0 before evaluating formulas
(salary_slip.py get_component_abbr_map), so a formula naming an abbreviation that no
earlier row in its own structure defines does not raise - it quietly computes as 0. With
remove_if_zero_valued the resulting row then disappears from the slip altogether. That is
how PAYE went missing while net pay looked plausible.
"""

import re
import sys

import frappe

if len(sys.argv) < 2:
	print(__doc__)
	raise SystemExit(1)

frappe.init(site=sys.argv[1])
frappe.connect()

components = {
	c.salary_component_abbr: c.name
	for c in frappe.get_all("Salary Component", fields=["name", "salary_component_abbr"])
	if c.salary_component_abbr
}
print("salary components: %d\n" % len(components))

IDENT = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
# a component name inside a quoted string is data, not an abbreviation reference
STRINGS = re.compile(r"'[^']*'|\"[^\"]*\"")
problems = 0

for st in frappe.get_all("Salary Structure", fields=["name", "docstatus", "is_active"]):
	assigned = frappe.db.count("Salary Structure Assignment",
	                           {"salary_structure": st.name, "docstatus": 1})
	rows = []
	for field in ("earnings", "deductions"):
		rows += frappe.get_all(
			"Salary Detail",
			filters={"parent": st.name, "parenttype": "Salary Structure", "parentfield": field},
			fields=["idx", "salary_component", "abbr", "condition", "formula", "parentfield"],
			order_by="idx",
		)

	defined = set()
	findings = []
	for r in rows:
		for expr, label in ((r.condition, "condition"), (r.formula, "formula")):
			for token in IDENT.findall(STRINGS.sub(" ", expr or "")):
				if token in components and token not in defined:
					findings.append(
						"      %s row %s %s names %r (%s) which no earlier row defines -> always 0"
						% (r.salary_component, r.idx, label, token, components[token]))
		if r.abbr:
			defined.add(r.abbr)

	for r in rows:
		master = frappe.db.get_value(
			"Salary Component", r.salary_component,
			["salary_component_abbr", "type"], as_dict=True) or frappe._dict()

		# a component master whose own abbr differs from the abbr used on the structure row
		if master.salary_component_abbr and r.abbr and master.salary_component_abbr != r.abbr:
			findings.append("      %s: structure abbr %r but component master abbr %r"
			                % (r.salary_component, r.abbr, master.salary_component_abbr))

		# which grid the row sits in decides whether it adds or subtracts - the master's
		# type is never consulted at slip time, so a Deduction parked under earnings is
		# added to gross instead of taken off it
		side = "Earning" if r.parentfield == "earnings" else "Deduction"
		if master.type and master.type != side:
			findings.append(
				"      %s: sits under %s so it is %s to pay, but the component is a %s"
				% (r.salary_component, r.parentfield,
				   "ADDED" if side == "Earning" else "SUBTRACTED", master.type))

	status = "docstatus=%s assignments=%s active=%s" % (st.docstatus, assigned, st.is_active)
	if findings:
		problems += 1
		print("  !! %-32s %s" % (st.name, status))
		for f in dict.fromkeys(findings):
			print(f)
	else:
		print("  ok %-32s %s" % (st.name, status))

print("\nstructures with findings: %d" % problems)
