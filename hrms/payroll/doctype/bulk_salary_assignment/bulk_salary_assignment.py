# Copyright (c) 2025, TMHS Group and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Coalesce
from frappe.query_builder.terms import SubQuery
from frappe.utils import flt, get_link_to_form

from hrms.hr.utils import validate_bulk_tool_fields
from hrms.payroll.doctype.salary_structure.salary_structure import (
	create_salary_structure_assignment,
)


class BulkSalaryAssignment(Document):
	def validate(self):
		for d in self.employees:
			if flt(d.base) <= 0:
				frappe.throw(_("Base salary must be greater than zero for employee {0}").format(d.employee_name or d.employee))
		self.calculate_totals()

	def calculate_totals(self):
		self.total_base = sum(flt(d.base) for d in self.employees)
		self.total_variable = sum(flt(d.variable) for d in self.employees)

	@frappe.whitelist()
	def update_employee(self, employee, key, value):
		employee = frappe.get_doc("Employee", employee)
		if key == "has_health_insurance" and value:
			employee.set("health_insurance", "NHIF (National Health Insurance Fund)")
			employee.set("health_insurance_percentage", 3)
		employee.set(key, value)
		employee.save()
	@frappe.whitelist()
	def get_employee_details(self, employee) -> dict:
		employee = frappe.get_doc("Employee", employee)
		return {
			"employee_name": employee.employee_name,
			"grade": employee.grade,
			"has_nssf": employee.has_nssf,
			"has_health_insurance": employee.has_health_insurance,
			"has_helsb": employee.has_helsb,
		}

	@frappe.whitelist()
	def get_employees(self, advanced_filters: list) -> list:
		quick_filter_fields = [
			"company",
			"employment_type",
			"branch",
			"department",
			"designation",
			"grade",
		]
		filters = [[d, "=", self.get(d)] for d in quick_filter_fields if self.get(d)]
		filters += advanced_filters

		Assignment = frappe.qb.DocType("Salary Structure Assignment")
		employees_with_assignments = SubQuery(
			frappe.qb.from_(Assignment)
			.select(Assignment.employee)
			.distinct()
			.where((Assignment.from_date == self.from_date) & (Assignment.docstatus == 1))
		)

		Employee = frappe.qb.DocType("Employee")
		query = frappe.qb.get_query(
			Employee,
			fields=[
				Employee.employee,
				Employee.employee_name,
				Employee.grade,
				Employee.has_nssf,
				Employee.has_health_insurance,
				Employee.has_helsb,
			],
			filters=filters,
		).where(
			(Employee.status == "Active")
			& (Employee.date_of_joining <= self.from_date)
			& ((Employee.relieving_date > self.from_date) | (Employee.relieving_date.isnull()))
			& (Employee.employee.notin(employees_with_assignments))
		)
		return query.run(as_dict=True)

	def on_submit(self):
		if not getattr(self, "employees", None):
			frappe.log_error(_("Please get and assign employees first before submitting."))
			frappe.throw(_("Please get and assign employees first before submitting."))

		mandatory_fields = ["salary_structure", "from_date", "company"]
		for field in mandatory_fields:
			if not self.get(field):
				frappe.log_error(_("{0} is mandatory").format(self.meta.get_label(field)))
				frappe.throw(_("{0} is mandatory").format(self.meta.get_label(field)))

		# Convert employees child table to dicts
		employees = []
		for d in self.employees:
			if d.base is None or d.base <= 0:
				frappe.throw(_("Base salary must be greater than zero for employee {0}").format(d.employee))
			employees.append({"employee": d.employee, "base": d.base, "variable": d.variable})

		if len(employees) <= 30:
			self._bulk_assign_structure(employees)
		else:
			frappe.enqueue(self._bulk_assign_structure, timeout=3000, employees=employees)
			frappe.msgprint(
				_("Creation of Salary Structure Assignments has been queued. It may take a few minutes."),
				alert=True,
				indicator="blue",
			)

	def _bulk_assign_structure(self, employees: list) -> None:
		success, failure = [], []
		count = 0
		savepoint = "before_salary_assignment"

		for d in employees:
			try:
				frappe.db.savepoint(savepoint)
				assignment = create_salary_structure_assignment(
					employee=d["employee"],
					salary_structure=self.salary_structure,
					company=self.company,
					currency=self.currency,
					payroll_payable_account=self.payroll_payable_account,
					from_date=self.from_date,
					base=d["base"],
					variable=d["variable"],
					income_tax_slab=self.income_tax_slab,
				)
			except Exception:
				frappe.db.rollback(save_point=savepoint)
				frappe.log_error(
					f"Bulk Assignment - Salary Structure Assignment failed for employee {d['employee']}.",
					reference_doctype="Salary Structure Assignment",
				)
				failure.append(d["employee"])
			else:
				success.append(
					{
						"doc": get_link_to_form("Salary Structure Assignment", assignment),
						"employee": d["employee"],
					}
				)

			count += 1
			frappe.publish_progress(count * 100 / len(employees), title=_("Assigning Structure..."))

		frappe.publish_realtime(
			"completed_bulk_salary_structure_assignment",
			message={"success": success, "failure": failure},
			doctype="Bulk Salary Assignment",
			after_commit=True,
		)

	@frappe.whitelist()
	def create_payroll_entry(self):
		if self.docstatus != 1:
			frappe.throw(_("Document must be submitted to create Payroll Entry"))

		if not getattr(self, "employees", None):
			frappe.throw(_("No employees found for this assignment"))
		# Get users with Signatory Role
		pe = frappe.new_doc("Payroll Entry")
		pe.company = self.company
		pe.title = self.title
		pe.currency = self.currency
		pe.payroll_payable_account = self.payroll_payable_account

		# Set posting date and payroll frequency
		pe.posting_date = self.from_date
		pe.payroll_frequency = "Monthly"

		# Compute start_date and end_date from payroll frequency
		from hrms.payroll.doctype.payroll_entry.payroll_entry import get_start_end_dates

		date_details = get_start_end_dates(pe.payroll_frequency, pe.posting_date, pe.company)
		pe.start_date = date_details.start_date
		pe.end_date = date_details.end_date

		# Set exchange rate: 1.0 if same currency, otherwise fetch rate
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		if self.currency and self.currency != company_currency:
			from erpnext.setup.utils import get_exchange_rate

			pe.exchange_rate = get_exchange_rate(self.currency, company_currency, pe.posting_date) or 1.0
		else:
			pe.exchange_rate = 1.0

		# Add employees to Payroll Entry
		for emp in self.employees:
			pe.append("employees", {"employee": emp.employee, "employee_name": emp.employee_name})

		# Populate sign_approvers if Payroll Entry has the sign workflow custom fields
		if frappe.get_meta("Payroll Entry").has_field("sign_approvers"):
			signatory_users = frappe.get_all(
				"Has Role",
				filters={"role": "Signatory", "parenttype": "User"},
				fields=["parent"],
			)

			if not signatory_users:
				frappe.throw(
					_(
						"No users with the 'Signatory' role found. Please assign the Signatory role to at least one user."
					)
				)

			for su in signatory_users:
				user = su.parent
				user_info = frappe.db.get_value("User", user, ["full_name", "email", "enabled"], as_dict=True)
				if not user_info or not user_info.enabled:
					continue
				pe.append(
					"sign_approvers",
					{
						"signer": user,
						"signer_name": user_info.full_name or user,
						"signer_email": user_info.email or user,
						"role": "SIGNER",
					},
				)

			if not pe.get("sign_approvers"):
				frappe.throw(
					_("No enabled users with the 'Signatory' role found. Cannot create Payroll Entry.")
				)

		pe.insert(ignore_permissions=True)
		return pe.name
