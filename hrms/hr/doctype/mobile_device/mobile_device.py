# Copyright (c) 2026, TMHS Group and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class MobileDevice(Document):
	def before_insert(self):
		self.registration_date = now_datetime()
		self.last_login = now_datetime()
		self.total_logins = 1

	def validate(self):
		self.validate_unique_employee_device()

	def validate_unique_employee_device(self):
		"""Ensure one active device per employee."""
		if not self.is_active:
			return

		existing = frappe.db.get_value(
			"Mobile Device",
			{
				"employee": self.employee,
				"is_active": 1,
				"name": ("!=", self.name),
			},
			"name",
		)

		if existing:
			frappe.throw(
				frappe._(
					"Employee {0} already has an active device ({1}). "
					"Deactivate it first before registering a new device."
				).format(self.employee, existing)
			)

	def update_login_stats(self):
		"""Called on each successful login to update analytics."""
		self.last_login = now_datetime()
		self.total_logins = (self.total_logins or 0) + 1
		self.save(ignore_permissions=True)

	def update_checkin_stats(self, location_label=None):
		"""Called on each successful check-in."""
		self.last_checkin_time = now_datetime()
		if location_label:
			self.last_checkin_location = location_label
		self.save(ignore_permissions=True)
