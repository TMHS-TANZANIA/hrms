# Copyright (c) 2026, TMHS Group and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today
from frappe.model.document import Document


class DisciplinaryResponse(Document):
	def validate(self):
		self.date = today()
	def on_submit(self):
		if self.remarks == "":
			frappe.throw("Remarks is Mandatory")
   
		doc=frappe.get_doc("Disciplinary Charge",self.disciplinary_charge)
		doc.respone_date = today()
		doc.save()
