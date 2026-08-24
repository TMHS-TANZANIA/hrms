# Copyright (c) 2026, TMHS Group and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from erpnext.setup.doctype.employee.test_employee import make_employee


def get_row(employee, name):
	rows = frappe.get_all(
		"Gross Salary History Item",
		filters={"parent": employee, "gross_salary_history": name},
		fields=["status", "gross_amount"],
	)
	return rows[0] if rows else None


class IntegrationTestGrossSalaryHistory(IntegrationTestCase):
	def test_row_is_synced_from_draft_to_approval(self):
		employee = make_employee("gross.salary.history@example.com")

		doc = frappe.get_doc(
			doctype="Gross Salary History",
			employee=employee,
			employee_name=frappe.db.get_value("Employee", employee, "employee_name"),
			gross_amount=1000,
			approver="Administrator",
			requester="Administrator",
			requester_name="Administrator",
		).insert()

		# visible while still waiting on the approver
		self.assertEqual(get_row(employee, doc.name).status, "Draft")
		self.assertFalse(frappe.db.get_value("Employee", employee, "gross_amount"))

		doc.submit()

		# same row, updated in place — not a duplicate
		self.assertEqual(get_row(employee, doc.name).status, "Approved")
		self.assertEqual(
			frappe.utils.flt(frappe.db.get_value("Employee", employee, "gross_amount")), 1000
		)
