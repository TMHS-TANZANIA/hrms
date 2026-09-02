// Copyright (c) 2025, TMHS Group and contributors
// For license information, please see license.txt
function paye_calculator(TAXABLE_INCOME) {
	let paye = 0;
	if (TAXABLE_INCOME < 270000) {
		paye = 0;
	}
	// rounded to whole shillings to match the Salary Structure's PAYE formula
	else if (TAXABLE_INCOME < 520000) {
		paye = flt(Math.round(0.08 * (TAXABLE_INCOME - 270000)));
	}
	else if (TAXABLE_INCOME < 760000) {
		paye = flt(Math.round(20000 + (0.2 * (TAXABLE_INCOME - 520000))))
	}
	else if (TAXABLE_INCOME < 1000000) {
		paye = flt(Math.round(68000 + (0.25 * (TAXABLE_INCOME - 760000))))
	}
	else {
		paye = flt(Math.round(128000 + (0.3 * (TAXABLE_INCOME - 1000000))))
	}
	return paye;
}
// the employee's own health insurance setting; a fixed amount beats a percentage,
// neither set falls back to NHIF at 3%
function health_insurance(row) {
	if (!row.has_health_insurance) return 0;
	if (flt(row.health_insurance_amount)) return flt(row.health_insurance_amount);
	const rate = flt(row.health_insurance_percentage) / 100 || 0.03;
	return flt(flt(row.base) * rate);
}

// calendar day proration: a joiner on the 15th of a 30 day month earns 16/30 of gross
function prorate(frm, row) {
	const divisor = cint(frm.doc.days_in_month);
	row.base = divisor ? flt(flt(row.monthly_gross) * cint(row.payable_days) / divisor) : 0;
}

// mirrors PAYE_EMPLOYMENT_TYPES and the PAYE condition on the Salary Structure
const PAYE_EMPLOYMENT_TYPES = ["Employment"];

// mirrors get_paye() on the server: PAYE is banded, not a percentage, so prorating the
// gross first would drop a part month employee into a lower band. Tax the whole month,
// then prorate the tax on the same ratio the gross was prorated on
function get_paye(row) {
	const gross = flt(row.monthly_gross);
	if (!gross || !PAYE_EMPLOYMENT_TYPES.includes(row.employment_type)) return 0;
	const full_nssf = row.has_nssf ? flt(gross * 0.1) : 0;
	return flt((paye_calculator(gross - full_nssf) * flt(row.base)) / gross);
}

frappe.ui.form.on("Bulk Salary Assignment", {
	setup(frm) {
		frm.trigger("set_queries");
		hrms.setup_employee_filter_group(frm);
	},
	async refresh(frm) {
		frm.page.clear_indicator();
		// the queued path reports its failures here; without this they are invisible and
		// only surface later as "no salary structure" on the Payroll Entry
		frappe.realtime.on("completed_bulk_salary_structure_assignment", (data) => {
			if (data.failure && data.failure.length)
				frappe.msgprint({
					title: __("Assignment Failed"),
					indicator: "red",
					message: __("Could not create a Salary Structure Assignment for: {0}", [
						frappe.utils.comma_and(data.failure),
					]),
				});
		});
		await frm.trigger("set_payroll_payable_account");

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Get Employees"), () => {
				frm.trigger("get_employees");
			});
		}

		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(__("Create Payroll Entry"), () => {
				frm.trigger("create_payroll_entry");
			});
		}
	},

	set_queries(frm) {
		frm.set_query("salary_structure", function () {
			return {
				filters: {
					company: frm.doc.company,
					is_active: "Yes",
					docstatus: 1,
				},
			};
		});
		frm.set_query("income_tax_slab", function () {
			return {
				filters: {
					company: frm.doc.company,
					disabled: 0,
					docstatus: 1,
					currency: frm.doc.currency,
				},
			};
		});
		frm.set_query("payroll_payable_account", function () {
			const company_currency = erpnext.get_currency(frm.doc.company);
			return {
				filters: {
					company: frm.doc.company,
					root_type: "Liability",
					is_group: 0,
					account_currency: ["in", [frm.doc.currency, company_currency]],
				},
			};
		});
	},
	from_date(frm) {
		if (!frm.doc.from_date) return;
		// a To Date left behind in the month From Date just moved away from makes the
		// period run backwards: total_working_days floors at 0, every row prorates to 0
		// days and the whole table zeroes out. Snap it back to the month being paid for
		const month_end = moment(frm.doc.from_date).endOf("month").format("YYYY-MM-DD");
		if (frm.doc.to_date >= frm.doc.from_date && frm.doc.to_date <= month_end) {
			frm.trigger("set_working_days");
			return;
		}
		// HR narrows To Date afterwards to pay part of a month; its handler recalculates
		frm.set_value("to_date", month_end);
	},

	to_date(frm) {
		frm.trigger("set_working_days");
	},

	set_period_days(frm) {
		if (!frm.doc.from_date) return;
		// an empty To Date means the whole month, the same default the server applies
		const end = frm.doc.to_date
			? moment(frm.doc.to_date)
			: moment(frm.doc.from_date).endOf("month");
		const days = end.diff(moment(frm.doc.from_date), "days") + 1;
		frm.set_value("total_working_days", Math.max(days, 0));
		// but the gross is always divided by the whole month, or a half month run would
		// divide 15 days by 15 and pay out a full month
		frm.set_value("days_in_month", moment(frm.doc.from_date).daysInMonth());
	},

	async set_working_days(frm) {
		if (!frm.doc.from_date) return;
		frm.trigger("set_period_days");
		if (!(frm.doc.employees || []).length) return;
		// payable days depend on each employee's joining and relieving date, which the row
		// does not carry, so the server recomputes them for the new period
		const r = await frm.call({ method: "refresh_payable_days", doc: frm.doc });
		frm.doc.employees.forEach((row) => {
			row.payable_days = cint(r.message[row.employee]);
			prorate(frm, row);
		});
		frm.refresh_field("employees");
		frm.trigger("calculate_totals");
	},

	set_payroll_payable_account(frm) {
		if (frm.doc.company) {
			frappe.db.get_value("Company", frm.doc.company, "default_payroll_payable_account", (r) => {
				frm.set_value("payroll_payable_account", r.default_payroll_payable_account);
			});
		}
	},

	get_employees(frm) {
		if (!frm.doc.from_date) {
			frappe.msgprint(__("Please select From Date."));
			return;
		}

		frm.call({
			method: "get_employees",
			args: {
				advanced_filters: frm.advanced_filters || [],
			},
			doc: frm.doc,
		}).then((r) => {
			if (r.message && r.message.length) {
				frm.trigger("set_period_days");
				frm.clear_table("employees");
				r.message.forEach((d) => {
					let row = frm.add_child("employees");
					row.employee = d.employee;
					row.employee_name = d.employee_name;
					row.employee_number = d.id || d.employee;
					row.monthly_gross = flt(d.gross_amount) || 0;
					row.payable_days = cint(d.payable_days);
					prorate(frm, row);
					row.child_support = flt(d.child_support);
					row.other_deduction = flt(d.other_deduction);
					row.health_insurance_amount = flt(d.health_insurance_amount);
					row.health_insurance_percentage = cint(d.health_insurance_percentage);
					row.employment_type = d.employment_type;
					row.variable = flt(d.variable) || 0;
					row.has_nssf = d.has_nssf;
					row.has_health_insurance = d.has_health_insurance;
					row.has_heslb = d.has_heslb;
				});
				// calculate_totals fills in nssf/nhif/heslb/paye/taxable_income/total_deductions
				frm.trigger("calculate_totals");
				frappe.msgprint(__("Employees fetched successfully."));
			} else {
				frappe.msgprint(__("No employees found based on the given filters."));
			}
		});
	},
	before_save(frm) {
		frm.trigger("calculate_totals");
	},
	calculate_totals(frm) {
		let total_base = 0;
		let total_nhif = 0;
		let total_heslb = 0;
		let total_nssf = 0;
		let total_variable = 0;
		let total_paye = 0;
		let total_company_nhif = 0;
		let total_company_nssf = 0;
		let grand_total_net_salary = 0;
		let total_sdl = 0;
		let total_wcf = 0;
		let total_child_support = 0;
		let total_other_deductions = 0;
		let total_deductions = 0;
		frm.doc.employees.forEach((row) => {
			total_base += flt(row.base);
			total_sdl += flt(row.base) * 0.035;
			total_wcf += flt(row.base) * 0.005;
			total_variable += flt(row.variable);
			row.nhif = health_insurance(row);
			if (row.has_health_insurance) {
				total_nhif += row.nhif;
				// Let take the maximum of 3% if the employee + company contribution is less than 40000, then the company will pay the remaining amount to make it 40000. To Ensure the contribution of the employee is always atleast 40k
				total_company_nhif += Math.max(row.nhif, 40000 - row.nhif);
			}
			if (row.has_heslb) {
				total_heslb += flt(row.base) * 0.15;
				row.heslb = flt(row.base) * 0.15;
			}
			else {
				row.heslb = 0;
			}
			if (row.has_nssf) {
				total_nssf += flt(row.base) * 0.1;
				row.nssf = flt(row.base) * 0.1;
				total_company_nssf += flt(row.base) * 0.1;
			}
			else {
				row.nssf = 0;
			}

			row.taxable_income = flt(flt(row.base) - flt(row.nssf));
			const paye = get_paye(row);
			row.paye = paye;
			row.total_deductions = flt(flt(row.nssf) + flt(row.nhif) + flt(row.heslb) + flt(row.paye) + flt(row.child_support) + flt(row.other_deduction));
			let net_salary = flt(flt(row.base) - flt(row.total_deductions));
			row.net_salary = flt(net_salary);
			grand_total_net_salary += flt(net_salary);
			total_paye += paye;
			total_child_support += flt(row.child_support);
			total_other_deductions += flt(row.other_deduction);
			total_deductions += flt(row.total_deductions);
		});
		frm.refresh_field("employees");
		frm.set_value("total_base", total_base);
		frm.set_value("total_nhif", total_nhif);
		frm.set_value("total_heslb", total_heslb);
		frm.set_value("total_nssf", total_nssf);
		frm.set_value("total_variable", total_variable);
		frm.set_value("total_paye", total_paye);
		frm.set_value("total_child_support", total_child_support);
		frm.set_value("total_other_deductions", total_other_deductions);
		frm.set_value("total_deductions", total_deductions);

		// Company Contributions
		frm.set_value("total_company_nhif", total_company_nhif);
		frm.set_value("total_company_nssf", total_company_nssf);
		frm.set_value("total_sdl", total_sdl);
		frm.set_value("total_wcf", total_wcf);
		// Set Grand Totals
		frm.set_value("grand_total_gross", total_base);
		frm.set_value("grand_total_nhif", total_nhif+total_company_nhif);
		frm.set_value("grand_total_nssf", total_nssf+total_company_nssf);
		frm.set_value("grand_total_net_salary", grand_total_net_salary);

	},

	create_payroll_entry(frm) {
		frappe.call({
			method: "create_payroll_entry",
			doc: frm.doc,
			callback: function (r) {
				if (r.message) {
					frappe.set_route("Form", "Payroll Entry", r.message);
				}
			}
		});
	}
});

frappe.ui.form.on("Bulk Salary Assignment Employee", {
	base(frm) {
		frm.trigger("calculate_totals");
	},
	has_health_insurance(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		update_employee(frm, row.employee, "has_health_insurance", row.has_health_insurance);
	},
	has_nssf(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		update_employee(frm, row.employee, "has_nssf", row.has_nssf);
	},
	has_heslb(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		update_employee(frm, row.employee, "has_heslb", row.has_heslb);
	},
	variable(frm) {
		frm.trigger("calculate_totals");
	},
	employees_remove(frm) {
		frm.trigger("calculate_totals");
	},
	employee(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (row.employee) {
			frappe.call({
				doc: frm.doc,
				method: "get_employee_details",
				args: {
					employee: row.employee,
				},
			}).then((r) => {
				if (r.message) {
					row.employee_name = r.message.employee_name;
					row.employee_number = r.message.id;
					row.monthly_gross = flt(r.message.gross_amount);
					row.payable_days = cint(r.message.payable_days);
					prorate(frm, row);
					row.child_support = flt(r.message.child_support);
					row.other_deduction = flt(r.message.other_deduction);
					row.health_insurance_amount = flt(r.message.health_insurance_amount);
					row.health_insurance_percentage = cint(r.message.health_insurance_percentage);
					row.employment_type = r.message.employment_type;
					row.variable = flt(r.message.variable);
					row.has_nssf = r.message.has_nssf;
					row.has_health_insurance = r.message.has_health_insurance;
					row.has_heslb = r.message.has_heslb;
					row.nssf = row.has_nssf ? flt(row.base * 0.1) : 0;
					row.heslb = row.has_heslb ? flt(row.base * 0.15) : 0;
					row.nhif = health_insurance(row);
					row.taxable_income = flt(flt(row.base) - flt(row.nssf));
					row.paye = get_paye(row);
					row.total_deductions = flt(flt(row.nssf) + flt(row.paye) + flt(row.nhif) + flt(row.heslb) + flt(row.child_support) + flt(row.other_deduction));
					row.net_salary = flt(flt(row.base) - flt(row.total_deductions));
					frm.refresh_field("employees");
					frm.trigger("calculate_totals");
				}
			});
		}
	},
});

function update_employee(frm, employee, key, value) {
	frm.call({
		doc: frm.doc,
		freeze: true,
		method: "update_employee",
		args: {
			employee: employee,
			key: key,
			value: value,
		},
		callback: function () {
			frm.trigger("calculate_totals");
		}
	});
}
