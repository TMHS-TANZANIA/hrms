# Copyright (c) 2026, TMHS Group and contributors
# For license information, please see license.txt

"""A deduction or reimbursement on a schedule, raised by HR and approved by the CEO.

The approved figures live on the Employee (refund / reimbursement and their dates), which
is what payroll reads. This document is the only writer of those fields: they are read
only on the Employee, so pay changes only through an approval. One adjustment of each
type is active per employee; approving a new one replaces the current one.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

# Employee field for the amount, deduct-on, from, to, and the adjustment that set them
EMPLOYEE_FIELDS = {
	"Deduction": ("refund", "deduction_on", "deduction_from", "deduction_to", "deduction_adjustment"),
	"Reimbursement": ("reimbursement", None, "reimbursement_from", "reimbursement_to", "reimbursement_adjustment"),
}


def months_touched(from_date, to_date) -> int:
	"""Calendar months the dates touch, partial ones included: 15 Oct to 2 Dec is 3."""
	start, end = getdate(from_date), getdate(to_date)
	return (end.year - start.year) * 12 + end.month - start.month + 1


class PayrollAdjustment(Document):
	def validate(self):
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date."))
		if self.type != "Deduction":
			self.deduct_on = None
		self.monthly_amount = (
			flt(self.amount) / months_touched(self.from_date, self.to_date)
			if self.amount_type == "Total Over Period"
			else flt(self.amount)
		)

	def on_submit(self):
		amount, deduct_on, from_field, to_field, link = EMPLOYEE_FIELDS[self.type]
		values = {amount: self.monthly_amount, from_field: self.from_date, to_field: self.to_date, link: self.name}
		if deduct_on:
			values[deduct_on] = self.deduct_on or "Net"
		frappe.db.set_value("Employee", self.employee, values)

	def on_cancel(self):
		amount, deduct_on, from_field, to_field, link = EMPLOYEE_FIELDS[self.type]
		# a newer adjustment may already have replaced this one; that one stays
		if frappe.db.get_value("Employee", self.employee, link) != self.name:
			return
		values = {amount: 0, from_field: None, to_field: None, link: None}
		if deduct_on:
			values[deduct_on] = "Net"
		frappe.db.set_value("Employee", self.employee, values)
