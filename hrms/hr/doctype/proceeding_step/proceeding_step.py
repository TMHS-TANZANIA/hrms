# Copyright (c) 2026, TMHS Group and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today
from frappe.model.document import Document


class ProceedingStep(Document):
	def validate(self):
		if not self.action_date and not self.to and not self.comments:
			frappe.throw("Please enter Action Date, To, and Comments")
   
		elif not self.action_date and not self.to:
			frappe.throw("Please enter Action Date and To.")

		elif not self.action_date and not self.comments:
			frappe.throw("Please enter Action Date and Comments.")

		elif not self.to and not self.comments:
			frappe.throw("Please enter To and Comments.")

		elif not self.action_date:
			frappe.throw("Please enter Action Date.")

		elif not self.to:
			frappe.throw("Please enter To.")

		elif not self.comments:
			frappe.throw("Please enter Comments.")
   
		
  
