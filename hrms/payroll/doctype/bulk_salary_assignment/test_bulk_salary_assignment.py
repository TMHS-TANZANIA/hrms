# Copyright (c) 2025, TMHS Group and Contributors
# See license.txt


import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase
from frappe.utils import getdate

from hrms.payroll.doctype.bulk_salary_assignment.bulk_salary_assignment import (
	BulkSalaryAssignment,
	apply_adjustments,
	apply_site_rate,
	get_health_insurance,
	get_payable_days,
	get_paye,
)


class TestPayableDays(IntegrationTestCase):
	"""Calendar day proration - the CEO's rule, not attendance based working days."""

	def test_payable_days(self):
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
		# contract end date on the Employee, no relieving date -> 1st..25th
		self.assertEqual(get_payable_days(start, end, "2020-01-01", None, "2026-04-25"), 25)
		# earlier of relieving and contract end wins
		self.assertEqual(get_payable_days(start, end, "2020-01-01", "2026-04-20", "2026-04-25"), 20)

		# 1,500,000 a month, joined on the 15th of a 30 day month
		self.assertEqual(1500000 * get_payable_days(start, end, "2026-04-15", None) / 30, 800000)


class TestHealthInsurance(IntegrationTestCase):
	"""Health insurance comes off the Employee record, not a hardcoded 3%."""

	def test_health_insurance(self):
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


class TestReversedPeriod(IntegrationTestCase):
	"""A To Date left behind in the previous month used to zero the whole table."""

	def test_period_running_backwards_pays_nobody(self):
		# From Date moved on to October while To Date stayed on 30 September: every
		# employee comes out with 0 payable days, whatever their joining date
		days = get_payable_days(getdate("2026-10-01"), getdate("2026-09-30"), "2020-01-01", None)
		self.assertEqual(days, 0)

		# which is why the client snaps To Date back to the end of From Date's month
		days = get_payable_days(getdate("2026-10-01"), getdate("2026-10-31"), "2020-01-01", None)
		self.assertEqual(days, 31)


class TestPayeOnFullGross(IntegrationTestCase):
	"""PAYE is banded, so the bands see the whole month and the tax is prorated after."""

	def row(self, gross, has_nssf=0):
		return frappe._dict(monthly_gross=gross, has_nssf=has_nssf, employment_type="Employment")

	def test_bands_see_the_whole_month(self):
		row = self.row(1500000)

		# a full month is taxed exactly as before
		self.assertEqual(get_paye(row, 1500000), 278000)

		# half a month owes half that tax, not the tax on half the gross: 750,000 falls in
		# the 20% band and would have been charged 66,000, i.e. 132,000 over the month
		self.assertEqual(get_paye(row, 750000), 139000)

		# and the halves still add back up to the full month's tax
		self.assertEqual(get_paye(row, 750000) + get_paye(row, 750000), 278000)

	def test_nssf_relief_is_a_whole_month_of_relief(self):
		# 10% NSSF off 1,500,000 leaves 1,350,000 taxable -> 128,000 + 30% of 350,000
		row = self.row(1500000, has_nssf=1)
		self.assertEqual(get_paye(row, 1500000), 233000)
		self.assertEqual(get_paye(row, 750000), 116500)

	def test_not_charged_where_it_does_not_apply(self):
		row = self.row(1500000)
		row.employment_type = "Consultant"
		self.assertEqual(get_paye(row, 1500000), 0)

		# no gross, no tax, and no ZeroDivisionError
		self.assertEqual(get_paye(self.row(0), 0), 0)


class TestReimbursement(IntegrationTestCase):
	"""Paid out separately from salary: summed on its own, never folded into gross or net."""

	def test_reimbursement_is_paid_on_top(self):
		doc = frappe._dict(
			employees=[
				frappe._dict(
					base=1000000,
					monthly_gross=1000000,
					employment_type="Employment",
					has_nssf=1,
					has_health_insurance=0,
					has_heslb=0,
					variable=0,
					child_support=0,
					other_deduction=0,
					reimbursement=50000,
					health_insurance_amount=0,
					health_insurance_percentage=0,
				)
			]
		)
		BulkSalaryAssignment.calculate_totals(doc)
		row = doc.employees[0]

		self.assertEqual(doc.total_reimbursement, 50000)
		# taxed on the base alone; the reimbursement is not in the taxable income
		self.assertEqual(row.taxable_income, 900000)
		# paid separately from salary, so neither the net nor the gross carries it
		self.assertEqual(row.net_salary, 1000000 - row.total_deductions)
		self.assertEqual(doc.grand_total_gross, 1000000)
		self.assertEqual(doc.grand_total_gross_with_reimbursement, 1050000)


class TestSiteRate(IntegrationTestCase):
	"""Site-rate employees are paid what the Site Sheet says, whole, then taxed like anyone."""

	def row(self, **kw):
		return frappe._dict({"employee": "EMP-1", "employee_name": "Site Guy", "employment_type": "Employment", **kw})

	def test_site_sheet_amount_is_the_base_unprorated(self):
		row = self.row()
		apply_site_rate(row, frappe._dict(days=12, amount=1500000))
		self.assertEqual((row.site_rate, row.payable_days, row.base, row.monthly_gross), (1, 12, 1500000, 1500000))
		# taxed on the whole amount: no proration ratio shrinks it
		self.assertEqual(get_paye(row, row.base), 278000)

	def test_not_on_a_site_sheet_pays_nothing(self):
		row = self.row()
		apply_site_rate(row, None)
		self.assertEqual((row.site_rate, row.payable_days, row.base), (1, 0, 0))

	def test_issues(self):
		doc = frappe._dict(employees=[
			self.row(employee="A", site_rate=1, base=0, monthly_gross=0, payable_days=0),
			self.row(employee="B", site_rate=0, base=0, monthly_gross=0, payable_days=30),
			self.row(employee="C", site_rate=0, base=0, monthly_gross=900000, payable_days=0),
			self.row(employee="D", site_rate=1, base=500000, monthly_gross=500000, payable_days=10),
			self.row(employee="E", site_rate=0, base=900000, monthly_gross=900000, payable_days=30),
		])
		doc.get_period = lambda: (getdate("2026-09-01"), getdate("2026-09-30"))
		from unittest.mock import patch

		with patch(
			"hrms.payroll.doctype.bulk_salary_assignment.bulk_salary_assignment.get_site_payrolls",
			return_value={"D": "SP-0001"},
		):
			issues = BulkSalaryAssignment.get_issues(doc)
		self.assertEqual(
			[(key, row.employee) for key, row, _extra in issues],
			[("no_site_sheet", "A"), ("no_gross", "B"), ("no_payable_days", "C"), ("site_payroll", "D")],
		)
		html = BulkSalaryAssignment.render_issues(doc, issues)
		self.assertIn("/app/engagement-agreement/new?employee=B", html)
		self.assertIn("/app/site-payroll/SP-0001", html)
		self.assertIn("Nothing to fix", BulkSalaryAssignment.render_issues(doc, []))


class TestAdjustments(UnitTestCase):
	"""Approved deductions/reimbursements apply only inside their dates; Gross ones cut the base."""

	start, end = getdate("2026-10-01"), getdate("2026-10-31")

	def emp(self, **kw):
		return frappe._dict({"refund": 100000, "deduction_on": "Net", "reimbursement": 50000, **kw})

	def test_net_deduction_and_reimbursement_in_window(self):
		row = frappe._dict()
		apply_adjustments(row, self.emp(deduction_from="2026-10-15", reimbursement_to="2026-10-01"), self.start, self.end)
		self.assertEqual((row.other_deduction, row.gross_deduction, row.reimbursement), (100000, 0, 50000))

	def test_outside_window_is_not_applied(self):
		row = frappe._dict()
		apply_adjustments(row, self.emp(deduction_to="2026-09-30", reimbursement_from="2026-11-01"), self.start, self.end)
		self.assertEqual((row.other_deduction, row.gross_deduction, row.reimbursement), (0, 0, 0))

	def test_gross_deduction_lowers_what_paye_sees(self):
		row = frappe._dict({"employment_type": "Employment", "monthly_gross": 1100000})
		apply_adjustments(row, self.emp(deduction_on="Gross"), self.start, self.end)
		self.assertEqual((row.other_deduction, row.gross_deduction), (0, 100000))
		# base 1,100,000 - 100,000 = 1,000,000 -> the same PAYE as a 1,000,000 gross
		self.assertEqual(get_paye(row, 1000000), get_paye(frappe._dict(employment_type="Employment", monthly_gross=1000000), 1000000))
