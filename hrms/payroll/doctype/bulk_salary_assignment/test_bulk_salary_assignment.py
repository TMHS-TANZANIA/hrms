# Copyright (c) 2025, TMHS Group and Contributors
# See license.txt


import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.doctype.bulk_salary_structure_assignment.bulk_salary_structure_assignment import (
	BulkSalaryStructureAssignment,
)
from hrms.payroll.doctype.salary_structure.test_salary_structure import make_salary_structure
from hrms.tests.test_utils import create_company, create_department, create_employee_grade
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from erpnext.setup.doctype.employee.test_employee import make_employee

from hrms.payroll.doctype.bulk_salary_structure_assignment.bulk_salary_structure_assignment import (
	BulkSalaryStructureAssignment,
)
from hrms.payroll.doctype.salary_structure.test_salary_structure import make_salary_structure
from hrms.tests.test_utils import create_company, create_department, create_employee_grade


class UnitTestBulkSalaryAssignment(UnitTestCase):
	def setUp(self):
		create_company()
		create_department("Accounts")
		self.grade = create_employee_grade("Test Grade")

		# employee grade with default base pay 50000
		self.emp1 = make_employee(
			"employee1@bssa.com", company="_Test Company", department="Accounts", grade="Test Grade"
		)
		self.emp2 = make_employee("employee2@bssa.com", company="_Test Company", department="Accounts")
		self.emp3 = make_employee("employee3@bssa.com", company="_Test Company", department="Accounts")
		# no department
		self.emp4 = make_employee("employee4@bssa.com", company="_Test Company")
		# different domain in employee_name
		self.emp5 = make_employee("employee5@test.com", company="_Test Company", department="Accounts")

	def tearDown(self):
		frappe.db.rollback()

	def test_get_employees(self):
		today = getdate()

		# create structure and assign to emp2
		make_salary_structure("Salary Structure 1", "Monthly", self.emp2, today, company="_Test Company")

		args = {
			"doctype": "Bulk Salary Structure Assignment",
			"from_date": today,
			"department": "Accounts",
		}
		bulk_assignment = BulkSalaryStructureAssignment(args)

		advanced_filters = [["Employee", "employee_name", "like", "%bssa%"]]
		employees = bulk_assignment.get_employees(advanced_filters)
		employee_names = [d.name for d in employees]

		# employee already having an assignment
		self.assertNotIn(self.emp2, employee_names)
		# department quick filter applied
		self.assertNotIn(self.emp4, employee_names)
		# employee_name advanced filter applied
		self.assertNotIn(self.emp5, employee_names)
		# employee grade default base pay fetched
		self.assertEqual(employees[0].base, self.grade.default_base_pay)
		# no employee grade
		self.assertEqual(employees[1].base, 0)
		self.assertEqual(len(employees), 2)

	def test_bulk_assign_structure(self):
		today = getdate()
		salary_structure = make_salary_structure("Salary Structure 1", "Monthly", company="_Test Company")

		args = {
			"doctype": "Bulk Salary Structure Assignment",
			"salary_structure": salary_structure.name,
			"from_date": today,
			"company": "_Test Company",
		}
		bulk_assignment = BulkSalaryStructureAssignment(args)

		employees = [
			{"employee": self.emp1, "base": 50000, "variable": 2000},
			{"employee": self.emp2, "base": 40000, "variable": 0},
		]
		bulk_assignment.bulk_assign_structure(employees)

		ssa1 = frappe.get_value(
			"Salary Structure Assignment",
			{"employee": self.emp1},
			["salary_structure", "from_date", "company", "base", "variable"],
			as_dict=1,
		)
		self.assertEqual(ssa1.salary_structure, salary_structure.name)
		self.assertEqual(ssa1.from_date, today)
		self.assertEqual(ssa1.company, "_Test Company")
		self.assertEqual(ssa1.base, 50000)
		self.assertEqual(ssa1.variable, 2000)

		ssa2 = frappe.get_value(
			"Salary Structure Assignment",
			{"employee": self.emp2},
			["base", "variable"],
			as_dict=1,
		)
		self.assertEqual(ssa2.base, 40000)
		self.assertEqual(ssa2.variable, 0)


class IntegrationTestBulkSalaryAssignment(IntegrationTestCase):
	"""
	Integration tests for BulkSalaryAssignment.
	Use this class for testing interactions between multiple components.
	"""

	pass


class TestPayableDays(IntegrationTestCase):
	"""Calendar day proration - the CEO's rule, not attendance based working days."""

	def test_payable_days(self):
		from hrms.payroll.doctype.bulk_salary_assignment.bulk_salary_assignment import get_payable_days

		start, end = getdate("2026-04-01"), getdate("2026-04-30")  # 30 days

		# employed for the whole month
		self.assertEqual(get_payable_days(start, end, "2020-01-01", None), 30)
		# joined on the 15th -> 15th..30th inclusive
		self.assertEqual(get_payable_days(start, end, "2026-04-15", None), 16)
		# contract ended on the 15th -> 1st..15th inclusive
		self.assertEqual(get_payable_days(start, end, "2020-01-01", "2026-04-15"), 15)
		# joined and left inside the month
		self.assertEqual(get_payable_days(start, end, "2026-04-10", "2026-04-19"), 10)
		# left before the month started
		self.assertEqual(get_payable_days(start, end, "2020-01-01", "2026-03-31"), 0)

		# 1,500,000 a month, joined on the 15th of a 30 day month
		self.assertEqual(1500000 * get_payable_days(start, end, "2026-04-15", None) / 30, 800000)


class TestHealthInsurance(IntegrationTestCase):
	"""Health insurance comes off the Employee record, not a hardcoded 3%."""

	def test_health_insurance(self):
		from hrms.payroll.doctype.bulk_salary_assignment.bulk_salary_assignment import (
			get_health_insurance,
		)

		row = frappe._dict(has_health_insurance=0, health_insurance_amount=0, health_insurance_percentage=0)
		self.assertEqual(get_health_insurance(row, 1000000), 0)

		# not configured on the Employee -> the old 3% NHIF behaviour is preserved
		row.has_health_insurance = 1
		self.assertEqual(get_health_insurance(row, 1000000), 30000)

		# a percentage on the Employee record wins over the default
		row.health_insurance_percentage = 5
		self.assertEqual(get_health_insurance(row, 1000000), 50000)

		# a fixed amount wins over the percentage
		row.health_insurance_amount = 45000
		self.assertEqual(get_health_insurance(row, 1000000), 45000)


class TestPartialPeriod(IntegrationTestCase):
	"""HR can pay part of a month; the divisor stays the whole month."""

	def test_half_month(self):
		from hrms.payroll.doctype.bulk_salary_assignment.bulk_salary_assignment import get_payable_days

		gross = 1500000

		# 1 to 15 August: 15 days paid for, but still divided by August's 31
		days = get_payable_days(getdate("2026-08-01"), getdate("2026-08-15"), "2020-01-01", None)
		self.assertEqual(days, 15)
		self.assertEqual(round(gross * days / 31), 725806)

		# 16 to 31 August is the other 16 days
		days = get_payable_days(getdate("2026-08-16"), getdate("2026-08-31"), "2020-01-01", None)
		self.assertEqual(days, 16)
		self.assertEqual(round(gross * days / 31), 774194)

		# the two halves add back up to the full month
		self.assertEqual(round(gross * 15 / 31) + round(gross * 16 / 31), gross)

		# a half month run that only overlaps the joiner's second week
		days = get_payable_days(getdate("2026-08-01"), getdate("2026-08-15"), "2026-08-10", None)
		self.assertEqual(days, 6)
