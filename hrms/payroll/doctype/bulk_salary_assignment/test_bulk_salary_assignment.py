# Copyright (c) 2025, TMHS Group and Contributors
# See license.txt


import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from hrms.payroll.doctype.bulk_salary_assignment.bulk_salary_assignment import (
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
