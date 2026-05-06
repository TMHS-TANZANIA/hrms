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
                });
                frm.refresh_field("employees");
                frappe.msgprint(__("Employees fetched successfully."));
            } else {
                frappe.msgprint(__("No employees found based on the given filters."));
            }
        });
    },

    create_payroll_entry(frm) {
        frappe.call({
            method: "create_payroll_entry",
            doc: frm.doc,
            callback: function(r) {
                if (r.message) {
                    frappe.set_route("Form", "Payroll Entry", r.message);
                }
            }
        });
    }
});
