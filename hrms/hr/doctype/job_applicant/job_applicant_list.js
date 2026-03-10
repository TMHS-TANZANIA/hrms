// Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and Contributors
// MIT License. See license.txt

frappe.listview_settings["Job Applicant"] = {
	add_fields: ["status", "email_id", "job_title", "applicant_name"],

	get_indicator: function (doc) {
		if (doc.status == "Accepted") {
			return [__(doc.status), "green", "status,=," + doc.status];
		} else if (["Open", "Replied"].includes(doc.status)) {
			return [__(doc.status), "orange", "status,=," + doc.status];
		} else if (["Hold", "Rejected"].includes(doc.status)) {
			return [__(doc.status), "red", "status,=," + doc.status];
		}
	},

	onload: function (listview) {
		listview.page.add_action_item(__("Send Shortlist Email"), function () {
			const selected = listview.get_checked_items();

			if (!selected || selected.length === 0) {
				frappe.msgprint({
					title: __("No Applicants Selected"),
					message: __("Please select at least one applicant from the list."),
					indicator: "orange",
				});
				return;
			}

			// Separate applicants with and without email
			const with_email = selected.filter((a) => a.email_id);
			const without_email_count = selected.length - with_email.length;

			if (with_email.length === 0) {
				frappe.msgprint({
					title: __("No Emails Found"),
					message: __("None of the selected applicants have an email address."),
					indicator: "red",
				});
				return;
			}

			const skipped_html =
				without_email_count > 0
					? `<div class="alert alert-warning mt-2" style="font-size:12px;">
						⚠️ <strong>${without_email_count}</strong> applicant(s) have no email and will be skipped.
					</div>`
					: "";

			const dialog = new frappe.ui.Dialog({
				title: __("Send Interview Shortlist Email"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<div style="padding: 8px 0;">
							<p style="margin:0;">Sending to <strong>${with_email.length}</strong> applicant(s).</p>
							${skipped_html}
						</div>`,
					},
					{
						label: __("Interview Date"),
						fieldname: "interview_date",
						fieldtype: "Date",
						reqd: 1,
					},
					{
						label: __("Interview Time"),
						fieldname: "interview_time",
						fieldtype: "Time",
					},
					{
						label: __("Interview Round"),
						fieldname: "interview_round",
						fieldtype: "Link",
						options: "Interview Round",
					},
					{
						label: __("Venue / Location or Meeting Link"),
						fieldname: "interview_location",
						fieldtype: "Data",
						placeholder: __("e.g. Boardroom Floor 2, or https://zoom.us/..."),
					},
					{
						fieldtype: "Section Break",
						label: __("Additional Message"),
					},
					{
						label: __("Additional Note (Optional)"),
						fieldname: "custom_message",
						fieldtype: "Small Text",
						placeholder: __(
							"Any extra instructions for the candidates, e.g. documents to bring, dress code..."
						),
					},
				],
				primary_action_label: __("Send Emails"),
				primary_action(values) {
					dialog.hide();

					frappe.call({
						method: "hrms.hr.doctype.job_applicant.job_applicant.send_shortlist_emails",
						args: {
							applicant_names: with_email.map((a) => a.name),
							interview_date: values.interview_date,
							interview_time: values.interview_time || null,
							interview_round: values.interview_round || null,
							interview_location: values.interview_location || null,
							custom_message: values.custom_message || null,
						},
						freeze: true,
						freeze_message: __("Sending emails, please wait..."),
						callback: function (r) {
							if (!r.exc && r.message) {
								const { sent, failed, errors } = r.message;
								let body = `<strong>${sent}</strong> email(s) sent successfully.`;
								if (failed > 0) {
									body += `<br><span style="color:red;">${failed} failed:</span><br>`;
									body +=
										"<small>" +
										(errors || [])
											.map((e) => frappe.utils.escape_html(e))
											.join("<br>") +
										"</small>";
								}
								frappe.msgprint({
									title: __("Shortlist Emails"),
									message: body,
									indicator: failed === 0 ? "green" : "orange",
								});
								listview.refresh();
							}
						},
					});
				},
			});

			dialog.show();
		});
	},
};
