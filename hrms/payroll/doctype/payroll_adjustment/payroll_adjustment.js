// Copyright (c) 2026, TMHS Group and contributors
// For license information, please see license.txt

// mirrors validate() on the server, which stays the authority on save
function set_monthly_amount(frm) {
	const { amount, amount_type, from_date, to_date } = frm.doc;
	if (amount_type !== "Total Over Period") {
		frm.set_value("monthly_amount", flt(amount));
		return;
	}
	if (!from_date || !to_date || to_date < from_date) return;
	// calendar months the dates touch, partial ones included, as months_touched() counts them
	const start = moment(from_date);
	const end = moment(to_date);
	const months = (end.year() - start.year()) * 12 + end.month() - start.month() + 1;
	frm.set_value("monthly_amount", flt(amount) / months);
}

frappe.ui.form.on("Payroll Adjustment", {
	amount: set_monthly_amount,
	amount_type: set_monthly_amount,
	from_date: set_monthly_amount,
	to_date: set_monthly_amount,
});
