# Copyright (c) 2026, TMHS Group and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GrossSalaryHistory(Document):
	def before_submit(self):
		self.approved_at = frappe.utils.now_datetime()

	def on_change(self):
		self.sync_to_employee()

	def sync_to_employee(self):
		"""Keep the row on Employee > Salary Assignment in sync, from draft to approval,
		so HR can see requests that are still waiting on an approver."""
		employee = frappe.get_doc("Employee", self.employee)

		row = next((r for r in employee.salary_assignment if r.gross_salary_history == self.name), None)
		if not row:
			row = employee.append("salary_assignment", {"gross_salary_history": self.name})

		row.update(
			{
				"gross_amount": self.gross_amount,
				"status": self.get("workflow_state") or ["Draft", "Approved", "Cancelled"][self.docstatus],
				"approver": self.approver,
				"approver_name": self.approver_name,
				"approved_at": self.approved_at,
				"requester": self.requester,
				"requester_name": self.requester_name,
				"requested_at": self.requested_at,
			}
		)

		if self.docstatus == 1:
			employee.gross_amount = self.gross_amount

		employee.save(ignore_permissions=True)

	def before_cancel(self):
		if frappe.session.user != "Administrator":
			frappe.throw("You cannot cancel this document. Please contact the system administrator for assistance.")
