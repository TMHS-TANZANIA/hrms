# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Self-check for the statutory report builders: run with the bench python,

	env/bin/python apps/hrms/hrms/payroll/test_statutory_reports.py

No site needed - the builders only read the templates and the rows handed to them.
"""

import datetime

import frappe
from frappe import _dict

from hrms.payroll import statutory_reports as sr

ROWS = [
	_dict(
		employee_name="Abasi Mohamed Hassani",
		first_name="Abasi",
		middle_name="Mohamed",
		last_name="Hassani",
		gender="Male",
		marital_status="Married",
		date_of_birth=datetime.date(1976, 2, 21),
		date_of_joining=datetime.date(2026, 1, 6),
		company_email="abasi@example.com",
		personal_email=None,
		cell_number="0715542113",
		designation="Driver",
		employment_type="Specific Task",
		tin_number="113-328-061",
		nssf_number="45041026",
		nhif_number="NH-1",
		wcf_number="605765910",
		nida_number="1976-0221-1111-2222",
		basic=2000000,
		nssf=200000,
		net_pay=1750000,
		reimbursement=50000,
		salary_mode="Bank",
		bank_name="NMB Bank Plc",
		bank_ac_no=" 123456789 ",
	)
]

BANK_ROWS = ROWS + [
	_dict(
		employee_name="Neema Juma",
		net_pay=900000,
		reimbursement=0,
		salary_mode="Bank",
		bank_name="Stanbic",
		bank_ac_no="98765432",
	),
	_dict(employee_name="Paid In Cash", salary_mode="Cash", net_pay=100000, reimbursement=0),
]

DOC = _dict(company="TMHS GROUP LIMITED", start_date="2026-08-01", end_date="2026-07-31")


def main():
	frappe.db = _dict(get_value=lambda *a, **kw: "120-487-906")

	paye = sr.build_paye(ROWS, DOC)["PAYE_EMPLOYEE"]
	assert paye["A1"].value == "SN", "template header row was overwritten"
	assert [c.value for c in paye[2]][:12] == [
		1,
		"113328061",
		"ABASI MOHAMED HASSANI",
		"1976022111112222",
		"Primary",
		"Resident",
		"45041026",
		2000000,
		0,
		0,
		200000,
		"Tanzania Mainland",
	], "PAYE row mismatch"

	sdl = sr.build_sdl(ROWS, DOC)
	assert sdl["INSTRUCTIONS"]["B4"].value == "2026"
	assert sdl["INSTRUCTIONS"]["B5"].value == "July"
	assert [c.value for c in sdl["Tanzania Mainland"][2]][:10] == [
		1,
		"113328061",
		"ABASI MOHAMED HASSANI",
		"1976022111112222",
		"Permanent",
		"Resident",
		2000000,
		0,
		0,
		"Tanzania Mainland",
	], "SDL row mismatch"

	nssf = sr.build_nssf(ROWS, DOC)["Template"]
	assert nssf["A1"].value == "SN"
	assert [c.value for c in nssf[2]] == [1, "45041026", "Abasi", "Mohamed", "Hassani", 2000000]

	wcf = sr.build_wcf(ROWS, DOC)["mySheet"]
	assert wcf["A1"].value == "wcf_number"
	assert [c.value for c in wcf[2]][:12] == [
		"605765910",
		"ABASI",
		"MOHAMED",
		"HASSANI",
		"MALE",
		datetime.date(1976, 2, 21),
		2000000,
		2000000,
		"Driver",
		"Specific Task",
		"1976022111112222",
		"0715542113",
	], "WCF row mismatch"
	assert wcf["J3"].value is None, "template hint row not cleared"

	nhif = sr.build_nhif(ROWS, DOC)["Employees List"]
	assert [c.value for c in nhif[1]] == sr.NHIF_COLUMNS
	assert [c.value for c in nhif[2]] == [
		"ABASI",
		"MOHAMED",
		"HASSANI",
		datetime.date(1976, 2, 21),
		"Male",
		"Married",
		"abasi@example.com",
		"0715542113",
		"1976022111112222",
		"605765910",
		datetime.date(2026, 1, 6),
		2000000,
	], "NHIF row mismatch"

	bank = sr.build_bank_transactions(BANK_ROWS, DOC)["Sheet1"]
	assert bank["A1"].value == "Beneficiary_Name"
	assert [c.value for c in bank[2]] == [
		"ABASI MOHAMED HASSANI",
		1700000,  # net pay less the reimbursement
		"123456789",
		"INTERNAL",
		"NMB BANK PLC",
		"salary",
		datetime.date(2026, 8, 1),
	], "bank row mismatch"
	assert [c.value for c in bank[3]][3:5] == ["DOMESTIC", "STANBIC"], "non-NMB must be domestic"
	assert bank["A4"].value is None, "cash-paid employee must not be in the bank file"

	thrown = []
	sr.frappe.throw = lambda msg, *a, **kw: thrown.append(msg)
	sr._ = lambda msg: msg
	sr.build_bank_transactions(
		[_dict(employee_name="No Account", salary_mode="Bank", net_pay=1, reimbursement=0, bank_ac_no="")],
		DOC,
	)
	assert thrown, "missing account number must throw"

	print("statutory reports ok")


if __name__ == "__main__":
	main()
