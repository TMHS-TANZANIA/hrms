// Copyright (c) 2026, TMHS Group and contributors
// For license information, please see license.txt

 frappe.ui.form.on("Disciplinary Offences", {
 	refresh(frm) {
         if (frm.is_new() && frm.doc.severity === "1") {
            frappe.prompt(
                [
                    {
                        label: "Select Severity",
                        fieldname: "Severity",
                        fieldtype: "Int",
                        options: ["2", "3"],
                        reqd: 1
                    }
                ],
                (values) => {
                    frm.set_value("severity", values.severity);
                },
                "Change Severity"
            );
        }
 	},
 });
