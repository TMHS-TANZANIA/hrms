// Copyright (c) 2025, TMHS Group and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bulk Salary Assignment", {
    setup(frm) {
        frm.trigger("set_queries");
        hrms.setup_employee_filter_group(frm);
    },

    async refresh(frm) {
        frm.page.clear_indicator();
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
                frm.clear_table("employees");
                r.message.forEach((d) => {
                    let row = frm.add_child("employees");
                    row.employee = d.employee;
                    row.employee_name = d.employee_name;
                    row.base = d.base;
                    row.variable = d.variable;
                    row.has_nssf = d.has_nssf;
                    row.has_health_insurance = d.has_health_insurance;
                    row.has_helsb = d.has_helsb;
                    console.log(d);
                });
                frm.refresh_field("employees");
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
        let paye_calculator = (TAXABLE_INCOME) => {
            paye = 0;
            if (TAXABLE_INCOME < 270000) {
                paye = 0;
            }
            else if (TAXABLE_INCOME < 520000) {
                paye = (0.08 * (TAXABLE_INCOME - 270000));
            }
            else if (TAXABLE_INCOME < 760000) {
                paye = (20000 + (0.2 * (TAXABLE_INCOME - 520000)))
            }
            else if (TAXABLE_INCOME < 1000000) {
                paye = (68000 + (0.25 * (TAXABLE_INCOME - 760000)))
            }
            else {
                paye = (128000 + (0.3 * (TAXABLE_INCOME - 1000000)))
            }
            return paye;
        }
        (frm.doc.employees || []).forEach((row) => {
            nssf = 0
            total_base += flt(row.base);
            total_variable += flt(row.variable);
            if (row.has_health_insurance) {
                total_nhif += flt(row.base) * 0.03;
            }
            if (row.has_helsb) {
                total_heslb += flt(row.base) * 0.15;
            }
            if (row.has_nssf) {
                nssf = flt(row.base) * 0.1;
                total_nssf += flt(row.base) * 0.1;
            }
            total_paye += paye_calculator(flt(row.base) + flt(row.variable) - nssf);
        });
        frm.set_value("total_base", total_base);
        frm.set_value("total_nhif", total_nhif);
        frm.set_value("total_heslb", total_heslb);
        frm.set_value("total_nssf", total_nssf);
        frm.set_value("total_variable", total_variable);
        frm.set_value("total_paye", total_paye);
    },
    paye_calculator(TAXABLE_INCOME) {
        paye = 0;
        if (TAXABLE_INCOME < 270000) {
            paye = 0;
        }
        else if (TAXABLE_INCOME < 520000) {
            paye = round(0.08 * (TAXABLE_INCOME - 270000));
        }
        else if (TAXABLE_INCOME < 760000) {
            paye = round(20000 + (0.2 * (TAXABLE_INCOME - 520000)))
        }
        else if (TAXABLE_INCOME < 1000000) {
            paye = round(68000 + (0.25 * (TAXABLE_INCOME - 760000)))
        }
        else {
            paye = round(128000 + (0.3 * (TAXABLE_INCOME - 1000000)))
        }
        return paye;
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
    has_helsb(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        update_employee(frm, row.employee, "has_helsb", row.has_helsb);
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
                    row.base = r.message.base;
                    row.variable = r.message.variable;
                    row.has_nssf = r.message.has_nssf;
                    row.has_health_insurance = r.message.has_health_insurance;
                    row.has_helsb = r.message.has_helsb;
                    frm.refresh_field("employees");
                    frm.trigger("calculate_totals");
                }
            });
        }
    },
});

function update_employee(frm, employee, key, value) {
    console.log("Updating employee", employee, key, value);
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
