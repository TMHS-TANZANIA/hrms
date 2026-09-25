# Copyright (c) 2026, TMHS Group and Contributors
# See license.txt

import frappe
from frappe.tests import UnitTestCase

from hrms.payroll.doctype.payroll_adjustment.payroll_adjustment import months_touched


class TestPayrollAdjustment(UnitTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_months_touched(self):
		self.assertEqual(months_touched("2026-10-01", "2027-03-31"), 6)
		self.assertEqual(months_touched("2026-10-15", "2026-12-02"), 3)
		self.assertEqual(months_touched("2026-10-01", "2026-10-31"), 1)

	def make(self, employee, **kw):
		return frappe.get_doc(
			{
				"doctype": "Payroll Adjustment",
				"employee": employee,
				"type": "Deduction",
				"amount_type": "Per Month",
				"amount": 100000,
				"from_date": "2026-10-01",
				"to_date": "2027-03-31",
				**kw,
			}
		)

	def test_monthly_amount(self):
		employee = frappe.get_all("Employee", limit=1, pluck="name")[0]
		doc = self.make(employee, amount_type="Total Over Period", amount=600000)
		doc.validate()
		self.assertEqual(doc.monthly_amount, 100000)
		doc = self.make(employee, type="Reimbursement", deduct_on="Gross")
		doc.validate()
		self.assertEqual((doc.monthly_amount, doc.deduct_on), (100000, None))

	def approve(self, doc):
		doc.insert()
		doc.submit()
		return doc

	def test_sync_replace_and_cancel(self):
		employee = frappe.get_all("Employee", limit=1, pluck="name")[0]
		fields = ["refund", "deduction_on", "deduction_from", "deduction_to", "deduction_adjustment"]
		first = self.approve(self.make(employee, deduct_on="Gross"))
		row = frappe.db.get_value("Employee", employee, fields, as_dict=True)
		self.assertEqual((row.refund, row.deduction_on, str(row.deduction_from), row.deduction_adjustment),
			(100000, "Gross", "2026-10-01", first.name))

		second = self.approve(self.make(employee, amount=50000))
		first.cancel()  # replaced already, so the Employee keeps the second one
		self.assertEqual(frappe.db.get_value("Employee", employee, "deduction_adjustment"), second.name)

		second.cancel()
		row = frappe.db.get_value("Employee", employee, fields, as_dict=True)
		self.assertEqual((row.refund, row.deduction_on, row.deduction_from, row.deduction_adjustment), (0, "Net", None, None))
