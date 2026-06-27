# Copyright (c) 2026, TMHS Group and contributors
# For license information, please see license.txt

from math import e

import frappe
from frappe.model.document import Document


class GrossSalaryHistory(Document):
	def before_submit(self,):
		employee = frappe.get_doc("Employee", self.employee)
		employee.append(
			"salary_assignment",
			{
				"gross_amount": self.gross_amount,
				"approver": self.approver,
				"approver_name": self.approver_name,
				"approved_at": frappe.utils.now_datetime(),
				"requester": self.requester,
				"requester_name": self.requester_name,
				"requested_at": self.requested_at,
				"gross_salary_history": self.name,
			}
		)
		employee.gross_amount = self.gross_amount
		employee.save(ignore_permissions=True)
	def before_cancel(self):
		if frappe.session.user != "Administrator":
			frappe.throw("You cannot cancel this document. Please contact the system administrator for assistance.")
