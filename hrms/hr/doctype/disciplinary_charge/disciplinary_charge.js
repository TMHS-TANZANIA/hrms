// Copyright (c) 2026, TMHS Group and contributors
// For license information, please see license.txt

 frappe.ui.form.on("Disciplinary Charge", {
    refresh(frm) {
        frm.add_custom_button("Disciplinary Response", () =>{
            frappe.call({
                method: "hrms.hr.doctype.disciplinary_charge.disciplinary_charge.make_displinary_response",
                args: {
                    docname: frm.doc.name
                },
                callback: (r) => {
                   frappe.set_route("Form","Disciplinary Response",r.message)
                }
            });
        });

         frm.add_custom_button("Investigation", () =>{
            frappe.call({
                method: "hrms.hr.doctype.disciplinary_charge.disciplinary_charge.make_displinary_investigation",
                args: {
                    docname: frm.doc.name
                },
                callback: (r) => {
                   frappe.set_route("Form","Disciplinary Investigation",r.message)
                }
            });
        });


         frm.add_custom_button("Proceeding Step", () =>{
            frappe.call({
                method: "hrms.hr.doctype.disciplinary_charge.disciplinary_charge.make_proceeding_step",
                args: {
                    displinary_charge_name: frm.doc.name
                },
                callback: (r) => {
                   frappe.set_route("Form","Proceeding Step",r.message)
                }
            });
        });
       
    }
});