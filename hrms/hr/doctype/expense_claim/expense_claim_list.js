frappe.listview_settings["Expense Claim"] = {
	add_fields: ["status", "approval_status", "total_sanctioned_amount", "total_amount_reimbursed", "is_paid", "docstatus"],
	get_indicator: function (doc) {
		if (doc.docstatus === 0) {
			return [__("Draft"), "red", "docstatus,=,0"];
		} else if (doc.docstatus === 2) {
			return [__("Cancelled"), "red", "docstatus,=,2"];
		} else if (doc.status === "Paid") {
			return [__("Paid"), "green", "status,=,Paid"];
		} else if (doc.status === "Unpaid" || doc.approval_status === "Approved") {
			return [__("Unpaid"), "orange", "status,=,Unpaid"];
		} else if (doc.status === "Rejected" || doc.approval_status === "Rejected") {
			return [__("Rejected"), "red", "status,=,Rejected"];
		} else if (doc.docstatus === 1 && doc.approval_status === "Draft") {
			return [__("Pending Approval"), "orange", "approval_status,=,Draft"];
		}
	},
};
