# Copyright (c) 2026, TMHS Group and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import today


class DisciplinaryCharge(Document):
   pass
   
   
@frappe.whitelist()
def make_displinary_response(docname):
    doc = frappe.get_doc("Disciplinary Charge", docname)
    dr = frappe.new_doc("Disciplinary Response")
    user = frappe.session.user
    employee = frappe.get_all("Employee",filters=[["user_id",'=',user]],fields=['name','employee_name'])
    if len(employee) < 1:
        frappe.throw("Your user account must be mapped with an employee")
    dr.employee = employee[0].name
    dr.date = today()
    dr.disciplinary_charge = doc.name
    dr.offence = doc.offence
    dr.offence_category = doc.offence_category
    dr.insert(ignore_permissions=True)
    return dr.name

@frappe.whitelist()
def make_displinary_investigation(docname):
    doc = frappe.get_doc("Disciplinary Charge", docname)
    iv = frappe.new_doc("Disciplinary Investigation")
    user = frappe.session.user
    employee = frappe.get_all("Employee",filters=[["user_id",'=',user]],fields=['name','employee_name'])
    if len(employee) < 1:
        frappe.throw("Your user account must be mapped with an employee")
    # iv.conductor_type = doc.conductor_type
    iv.employee = employee[0].name
    iv.conductor_full_name = doc.employees_name
    iv.disciplinary_charge = doc.name
    # iv.conductor_email = doc.conductor_email
    # iv.conductor_phone = doc.conductor_phone
    # iv.department = doc.department
    iv.insert(ignore_permissions=True)
    return iv.name

@frappe.whitelist()
def make_proceeding_step(displinary_charge_name):
    from frappe.model.mapper import get_mapped_doc
    di = frappe.get_all(
    "Disciplinary Investigation",
    filters={
        "disciplinary_charge": displinary_charge_name
    },
    fields=["name","employee","conductor_full_name","conductor_email","conductor_phone","remarks","department"]
)   
    dr = frappe.get_all("Disciplinary Response",filters = {
        "disciplinary_charge": displinary_charge_name
    },fields=["*"])
        
    ps = frappe.new_doc("Proceeding Step")
    ps.date = today()
    # Involved Person Details
    ps.employee = dr[0].employee
    ps.disciplinary_charge = displinary_charge_name
    ps.response = dr[0].name
    ps.offence_category = dr[0].offence_category
    ps.offence = dr[0].offence
    ps.remarks= dr[0].remarks
    # Investigation Details
    ps.type = di[0].conductor_type
    ps.investigator_employee = di[0].employee
    ps.disciplinary_investigation = di[0].name
    ps.full_name = di[0].conductor_full_name
    ps.phone = di[0].conductor_phone
    ps.email = di[0].conductor_email
    ps.department = di[0].department
    
    ps.status = "INCOMPL" #Status is In Progress by default
    dc = frappe.get_single("Disciplinary Commitee")
    for row in dc.commitee_members:
        ps.append("disciplinary_committee",{
            "employee":row.employee,
            "fullname":row.fullname,
            "company":row.company,
            "phone_number":row.phone_number,
            "email":row.email,
            "department":row.department,
        })
    
    ps.insert(ignore_permissions=True)
    return ps.name

    
    
