# Copyright (c) 2025, TMHS Group and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.custom import ConstantColumn
from frappe.query_builder.functions import Coalesce
from frappe.query_builder.terms import SubQuery
from frappe.utils import date_diff, flt, get_first_day, get_last_day, get_link_to_form, getdate

from hrms.hr.utils import validate_bulk_tool_fields
from hrms.payroll.doctype.salary_structure.salary_structure import (
	create_salary_structure_assignment,
)


NSSF_RATE = 0.1
NHIF_RATE = 0.03
HESLB_RATE = 0.15
SDL_RATE = 0.035
WCF_RATE = 0.005
MIN_NHIF_CONTRIBUTION = 40000


# employment types that attract PAYE. Kept in step with the PAYE condition on the Salary
# Structure; if the two drift, the Payroll Entry and the Salary Slip stop agreeing.
PAYE_EMPLOYMENT_TYPES = ("Employment",)


def is_paye_applicable(employment_type) -> bool:
	return employment_type in PAYE_EMPLOYMENT_TYPES


def calculate_paye(taxable_income: float) -> float:
	# rounded to whole shillings, the same as the PAYE formula on the Salary Structure;
	# without this the Payroll Entry and the Salary Slip drift by cents
	taxable_income = flt(taxable_income)
	if taxable_income < 270000:
		return 0.0
	if taxable_income < 520000:
		return flt(round(0.08 * (taxable_income - 270000)))
	if taxable_income < 760000:
		return flt(round(20000 + 0.2 * (taxable_income - 520000)))
	if taxable_income < 1000000:
		return flt(round(68000 + 0.25 * (taxable_income - 760000)))
	return flt(round(128000 + 0.3 * (taxable_income - 1000000)))


EMPLOYEE_FIELDS = [
	"name",
	"date_of_joining",
	"relieving_date",
	"has_child_support",
	"child_support_amount",
	"refund",
	"health_insurance_amount",
	"health_insurance_percentage",
	"employment_type",
]


def get_health_insurance(row, base: float) -> float:
	"""The employee's own health insurance setting, falling back to the 3% NHIF rate.

	A fixed amount on the Employee record wins over a percentage; neither set means NHIF
	at 3%, which is what every employee was charged before these fields were read.
	"""
	if not row.has_health_insurance:
		return 0.0
	if flt(row.health_insurance_amount):
		return flt(row.health_insurance_amount)
	rate = flt(row.health_insurance_percentage) / 100 or NHIF_RATE
	return flt(base * rate)


def get_payable_days(start, end, date_of_joining=None, relieving_date=None) -> int:
	"""Calendar days the employee is engaged for inside [start, end], both ends inclusive."""
	first = max(getdate(date_of_joining), start) if date_of_joining else start
	last = min(getdate(relieving_date), end) if relieving_date else end
	return max(date_diff(last, first) + 1, 0)


class BulkSalaryAssignment(Document):
	def validate(self):
		if self.to_date and getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To Date cannot be before From Date"))
		missing = [d.employee_name or d.employee for d in self.employees if flt(d.monthly_gross) <= 0]
		if missing:
			# one message for the whole table; throwing on the first row means finding the
			# rest one save at a time
			frappe.throw(
				_("Monthly gross must be greater than zero for: {0}").format(", ".join(missing))
			)
		self.sync_from_employee()
		self.calculate_totals()

	def get_period(self) -> tuple:
		"""The stretch of days being paid for. Defaults to the whole month of From Date."""
		start = getdate(self.from_date)
		return start, getdate(self.to_date) if self.to_date else get_last_day(start)

	def sync_from_employee(self):
		"""Prorate on calendar days and pull the Other Deductions off the Employee record.

		Payable days are the days the employee is actually engaged within the month, so a
		joiner on the 15th of a 30 day month is paid 16/30 of their monthly gross and a
		leaver on the 15th is paid 15/30. Narrowing From Date/To Date to part of a month
		prorates the same way, so paying 1 to 15 August gives 15/31. NSSF/NHIF/HESLB/PAYE
		follow because they all derive from `base`. Child support and the "Deduction"
		field are fixed monthly amounts, so they are taken whole and are not prorated.
		"""
		start, end = self.get_period()
		self.total_working_days = date_diff(end, start) + 1

		# the divisor is always the whole month, never the length of the period being paid
		# for, otherwise a half month run would divide 15 days by 15 and pay a full gross
		month_start = get_first_day(self.from_date)
		self.days_in_month = date_diff(get_last_day(month_start), month_start) + 1

		employees = {}
		if self.employees:
			employees = {
				d.name: d
				for d in frappe.get_all(
					"Employee",
					filters={"name": ("in", [d.employee for d in self.employees])},
					fields=EMPLOYEE_FIELDS,
				)
			}

		for d in self.employees:
			emp = employees.get(d.employee) or frappe._dict()
			d.payable_days = get_payable_days(start, end, emp.date_of_joining, emp.relieving_date)
			d.base = flt(d.monthly_gross) * d.payable_days / self.days_in_month
			d.child_support = flt(emp.child_support_amount) if emp.has_child_support else 0.0
			d.other_deduction = flt(emp.refund)
			d.health_insurance_amount = flt(emp.health_insurance_amount)
			d.health_insurance_percentage = emp.health_insurance_percentage
			d.employment_type = emp.employment_type

	def calculate_totals(self):
		"""Recompute every row and every summary field.

		This is the authority for the numbers: the client mirrors it for live feedback,
		but the row fields are read only, so nothing else can set them.
		"""
		totals = dict.fromkeys(
			[
				"total_base",
				"total_variable",
				"total_nssf",
				"total_nhif",
				"total_heslb",
				"total_paye",
				"total_child_support",
				"total_other_deductions",
				"total_deductions",
				"total_company_nssf",
				"total_company_nhif",
				"total_sdl",
				"total_wcf",
				"grand_total_net_salary",
			],
			0.0,
		)

		for d in self.employees:
			base = flt(d.base)

			d.nssf = flt(base * NSSF_RATE) if d.has_nssf else 0.0
			d.nhif = get_health_insurance(d, base)
			d.heslb = flt(base * HESLB_RATE) if d.has_heslb else 0.0
			d.taxable_income = flt(base - d.nssf)
			d.paye = calculate_paye(d.taxable_income) if is_paye_applicable(d.employment_type) else 0.0
			d.total_deductions = flt(
				d.nssf + d.nhif + d.heslb + d.paye + flt(d.child_support) + flt(d.other_deduction)
			)
			d.net_salary = flt(base - d.total_deductions)

			totals["total_base"] += base
			totals["total_variable"] += flt(d.variable)
			totals["total_nssf"] += d.nssf
			totals["total_nhif"] += d.nhif
			totals["total_heslb"] += d.heslb
			totals["total_paye"] += d.paye
			totals["total_child_support"] += flt(d.child_support)
			totals["total_other_deductions"] += flt(d.other_deduction)
			totals["total_deductions"] += d.total_deductions
			totals["total_sdl"] += flt(base * SDL_RATE)
			totals["total_wcf"] += flt(base * WCF_RATE)
			totals["grand_total_net_salary"] += d.net_salary

			if d.has_nssf:
				totals["total_company_nssf"] += flt(base * NSSF_RATE)
			if d.has_health_insurance:
				# the company matches the employee's 3%, except where that leaves the
				# combined contribution under the 40,000 minimum: then it pays the gap
				# instead. Above a base of 666,667 the plain 3% already clears the
				# minimum, so no top up applies.
				totals["total_company_nhif"] += max(d.nhif, MIN_NHIF_CONTRIBUTION - d.nhif)

		self.update(totals)
		self.grand_total_gross = totals["total_base"]
		self.grand_total_nssf = totals["total_nssf"] + totals["total_company_nssf"]
		self.grand_total_nhif = totals["total_nhif"] + totals["total_company_nhif"]

	@frappe.whitelist()
	def refresh_payable_days(self) -> dict:
		"""Payable days per employee for the current period, keyed by employee.

		The grid row carries no joining or relieving date, so the client cannot work this
		out for itself. It used to clamp the previous value against the period length
		instead, which drove every row to 0 days whenever To Date was left behind in a
		month that From Date had already moved away from.
		"""
		self.sync_from_employee()
		return {d.employee: d.payable_days for d in self.employees}

	@frappe.whitelist()
	def update_employee(self, employee, key, value):
		employee = frappe.get_doc("Employee", employee)
		if key == "has_health_insurance" and value and not employee.health_insurance:
			# only seed a default; never overwrite the provider or rate HR already picked
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
			"has_heslb": employee.has_helsb,
			"gross_amount": employee.gross_amount,
			"child_support": flt(employee.child_support_amount) if employee.has_child_support else 0.0,
			"other_deduction": flt(employee.refund),
			"health_insurance_amount": flt(employee.health_insurance_amount),
			"health_insurance_percentage": employee.health_insurance_percentage,
			"employment_type": employee.employment_type,
			"payable_days": get_payable_days(
				*self.get_period(), employee.date_of_joining, employee.relieving_date
			),
			"id": employee.name,
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
		start, end = self.get_period()

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
				# the Employee field is spelled "helsb"; alias it so the client gets the
				# same "has_heslb" key that the child table and get_employee_details use
				Employee.has_helsb.as_("has_heslb"),
				Employee.gross_amount,
				Employee.date_of_joining,
				Employee.relieving_date,
				Employee.has_child_support,
				Employee.child_support_amount,
				Employee.refund,
				Employee.health_insurance_amount,
				Employee.health_insurance_percentage,
				Employee.employment_type,
			],
			filters=filters,
		).where(
			(Employee.status.isin(["Active", "Left"]))
			& (Employee.date_of_joining <= end)
			& ((Employee.relieving_date >= start) | (Employee.relieving_date.isnull()))
			& (Employee.employee.notin(employees_with_assignments))
		)

		rows = query.run(as_dict=True)
		for d in rows:
			d.payable_days = get_payable_days(start, end, d.date_of_joining, d.relieving_date)
			d.child_support = flt(d.child_support_amount) if d.has_child_support else 0.0
			d.other_deduction = flt(d.refund)
		return rows

	def on_submit(self):
		if not getattr(self, "employees", None):
			frappe.log_error(_("Please get and assign employees first before submitting."))
			frappe.throw(_("Please get and assign employees first before submitting."))

		mandatory_fields = ["salary_structure", "from_date", "company"]
		for field in mandatory_fields:
			if not self.get(field):
				frappe.log_error(_("{0} is mandatory").format(self.meta.get_label(field)))
				frappe.throw(_("{0} is mandatory").format(self.meta.get_label(field)))

		assignment_dates = self.get_assignment_dates()

		employees = []
		for d in self.employees:
			if d.base is None or d.base <= 0:
				frappe.throw(_("Base salary must be greater than zero for employee {0}").format(d.employee))

			# the Salary Structure Assignment carries the full monthly rate, not the prorated
			# amount. "Basic" depends on payment days, so the Salary Slip prorates it once
			# from this rate; storing the prorated figure here would prorate it twice.
			employees.append(
				{
					"employee": d.employee,
					"base": flt(d.monthly_gross) or flt(d.base),
					"variable": d.variable,
					"from_date": assignment_dates[d.employee],
				}
			)

		if len(employees) <= 30:
			self._bulk_assign_structure(employees)
		else:
			frappe.enqueue(self._bulk_assign_structure, timeout=3000, employees=employees)
			frappe.msgprint(
				_("Creation of Salary Structure Assignments has been queued. It may take a few minutes."),
				alert=True,
				indicator="blue",
			)

	def get_assignment_dates(self) -> dict:
		"""employee -> the date its Salary Structure Assignment starts on.

		A Salary Structure Assignment cannot start before the employee did, so a mid month
		joiner is assigned from their joining date rather than from the period start.
		"""
		from_date = getdate(self.from_date)
		joining_dates = dict(
			frappe.get_all(
				"Employee",
				filters={"name": ("in", [d.employee for d in self.employees])},
				fields=["name", "date_of_joining"],
				as_list=True,
			)
		)
		return {
			d.employee: max(getdate(joining_dates[d.employee]), from_date)
			if joining_dates.get(d.employee)
			else from_date
			for d in self.employees
		}

	def on_cancel(self):
		"""Cancel the Salary Structure Assignments this document created.

		Without this an amended copy cannot be resubmitted: every employee still holds an
		assignment on the same date, so DuplicateAssignment sends all of them to `failure`
		and the amendment silently does nothing.
		"""
		for employee, from_date in self.get_assignment_dates().items():
			name = frappe.db.get_value(
				"Salary Structure Assignment",
				{
					"employee": employee,
					"salary_structure": self.salary_structure,
					"from_date": from_date,
					"docstatus": 1,
				},
			)
			if name:
				frappe.get_doc("Salary Structure Assignment", name).cancel()

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
					from_date=d["from_date"],
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

		if failure:
			frappe.msgprint(
				_("Could not create a Salary Structure Assignment for: {0}. Payroll Entry will not pick them up.").format(
					frappe.bold(", ".join(failure))
				),
				title=_("Assignment Failed"),
				indicator="red",
			)

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
		pe.total_variable = self.total_variable
		pe.total_nhif = self.total_nhif
		pe.total_nssf = self.total_nssf
		pe.total_heslb = self.total_heslb
		pe.total_paye = self.total_paye
		pe.total_gross_summary = self.total_base
		pe.grand_total_net_salary = self.grand_total_net_salary
		pe.bulk_salary_assignment = self.name
		# Set total company contributions
		pe.total_company_nhif = self.total_company_nhif
		pe.total_company_nssf = self.total_company_nssf
		pe.total_sdl = self.total_sdl
		pe.total_wcf = self.total_wcf

		# Set grand totals
		pe.grand_total_nssf = self.grand_total_nssf
		pe.grand_total_nssf = self.grand_total_nssf
		pe.grand_total_nhif = self.grand_total_nhif
		pe.grand_total_gross = self.grand_total_gross

		# Set posting date and payroll frequency
		pe.posting_date = self.from_date
		pe.payroll_frequency = "Monthly"

		# Compute start_date and end_date from payroll frequency
		pe.start_date, pe.end_date = self.get_period()

		# Set exchange rate: 1.0 if same currency, otherwise fetch rate
		company_currency = frappe.db.get_value("Company", self.company, "default_currency")
		if self.currency and self.currency != company_currency:
			from erpnext.setup.utils import get_exchange_rate

			pe.exchange_rate = get_exchange_rate(self.currency, company_currency, pe.posting_date) or 1.0
		else:
			pe.exchange_rate = 1.0

		# Add employees to Payroll Entry
		for emp in self.employees:
			pe.append(
				"employees",
				{
					"employee": emp.employee,
					"employee_name": emp.employee_name,
					"base": emp.base,
					"nssf": emp.nssf,
					"paye": emp.paye,
					"nhif": emp.nhif,
					"heslb": emp.heslb,
					"net_salary": emp.net_salary,
					"taxable_income": emp.taxable_income,
					"total_deductions": emp.total_deductions,
				},
			)

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
