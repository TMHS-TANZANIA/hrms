// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Leave Application", {
	setup: function (frm) {
		frm.set_query("leave_approver", function () {
			return {
				query: "hrms.hr.doctype.department_approver.department_approver.get_approvers",
				filters: {
					employee: frm.doc.employee,
					doctype: frm.doc.doctype,
				},
			};
		});
		frm.set_query("employee", erpnext.queries.employee);
	},

	onload: function (frm) {
		// Ignore cancellation of doctype on cancel all.
		frm.ignore_doctypes_on_cancel_all = ["Leave Ledger Entry"];

		if (!frm.doc.posting_date) {
			frm.set_value("posting_date", frappe.datetime.get_today());
		}
		if (frm.doc.docstatus == 0) {
			return frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.get_mandatory_approval",
				args: {
					doctype: frm.doc.doctype,
				},
				callback: function (r) {
					if (!r.exc && r.message) {
						frm.toggle_reqd("leave_approver", true);
					}
				},
			});
		}
	},

	validate: function (frm) {
		if (frm.doc.from_date === frm.doc.to_date && cint(frm.doc.half_day)) {
			frm.doc.half_day_date = frm.doc.from_date;
		} else if (frm.doc.half_day === 0) {
			frm.doc.half_day_date = "";
		}
		frm.toggle_reqd("half_day_date", cint(frm.doc.half_day));
	},

	make_dashboard: function (frm) {
		let leave_details;
		let lwps;

		if (frm.doc.employee) {
			frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.get_leave_details",
				async: false,
				args: {
					employee: frm.doc.employee,
					date: frm.doc.from_date || frm.doc.posting_date,
				},
				callback: function (r) {
					if (!r.exc && r.message["leave_allocation"]) {
						leave_details = r.message["leave_allocation"];
					}
					lwps = r.message["lwps"];
				},
			});

			$("div").remove(".form-dashboard-section.custom");

			frm.dashboard.add_section(
				frappe.render_template("leave_application_dashboard", {
					data: leave_details,
				}),
				__("Allocated Leaves"),
			);
			frm.dashboard.show();

			let allowed_leave_types = Object.keys(leave_details);
			// lwps should be allowed for selection as they don't have any allocation
			allowed_leave_types = allowed_leave_types.concat(lwps);

			frm.set_query("leave_type", function () {
				return {
					filters: [["leave_type_name", "in", allowed_leave_types]],
				};
			});
		}
	},


	refresh: function (frm) {
		hrms.leave_utils.add_view_ledger_button(frm);
		if (frm.is_new()) {
			frm.trigger("calculate_total_days");
		}

		frm.set_intro("");
		if (frm.doc.__islocal && !in_list(frappe.user_roles, "Employee")) {
			frm.set_intro(__("Fill the form and save it"));
		} else if (
			frm.perm[0] &&
			frm.perm[0].submit &&
			!frm.is_dirty() &&
			!frm.is_new() &&
			!frappe.model.has_workflow(frm.doctype) &&
			frm.doc.docstatus === 0
		) {
			frm.set_intro(__("Submit this Leave Application to confirm."));
		}

		frm.trigger("set_employee");
		if (frm.doc.docstatus === 0) {
			frm.trigger("make_dashboard");
		}
		frm.trigger("set_form_buttons");
		frm.trigger("handle_submit_button");
		frm.trigger("ensure_approval_chain");

	
		// Show approve/reject buttons for current approver (Material Request style)
		console.log("Debug - Session User:", frappe.session.user);
		console.log("Debug - Status:", frm.doc.status);
		console.log("Debug - Docstatus:", frm.doc.docstatus);
		console.log("Debug - Approvers:", frm.doc.approvers);
		
		// Check if current user is in the approvers table and has New status (Material Request style)
		let is_current_approver = false;
		if (frm.doc.approvers && frm.doc.approvers.length > 0) {
			for (let approver of frm.doc.approvers) {
				if (approver.approver === frappe.session.user && approver.status === "New") {
					is_current_approver = true;
					break;
				}
			}
		}
		
		if (frm.doc.docstatus === 0 && is_current_approver && 
			(frm.doc.status === "Open" || frm.doc.status === "Pending Approval" || frm.doc.status === "Applied")) {
			
			frm.add_custom_button(__("Approve"), function () {
				frappe.prompt(
					[
						{
							fieldname: "comments",
							fieldtype: "Small Text",
							label: __("Comments (Optional)"),
							reqd: 0,
						},
					],
					function (values) {
						frappe.call({
							method: "hrms.hr.doctype.leave_application.leave_application.approve_application",
							args: {
								name: frm.doc.name,
								comments: values.comments,
							},
							callback: function (r) {
								if (!r.exc) {
									frm.reload_doc();
								}
							},
						});
					},
					__("Approve Leave Application"),
					__("Approve")
				);
			}, "Actions");

			frm.add_custom_button(__("Reject"), function () {
				frappe.prompt(
					[
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Reason for Rejection"),
							reqd: 1,
						},
						{
							fieldname: "comments",
							fieldtype: "Small Text",
							label: __("Additional Comments (Optional)"),
							reqd: 0,
						},
					],
					function (values) {
						frappe.call({
							method: "hrms.hr.doctype.leave_application.leave_application.reject_application",
							args: {
								name: frm.doc.name,
								reason: values.reason,
								comments: values.comments,
							},
							callback: function (r) {
								if (!r.exc) {
									frm.reload_doc();
								}
							},
						});
					},
					__("Reject Leave Application"),
					__("Reject")
				);
			}, "Actions");
		}
	},

	handle_submit_button: function (frm) {
		// Hide submit button if approval chain exists and current user is not the applicant
		if (frm.doc.approval_chain && frm.doc.approval_chain.length > 0) {
			// Check if current user is the applicant
			frappe.db.get_value("Employee", frm.doc.employee, "user_id", (r) => {
				if (frappe.session.user !== r.user_id) {
					// Hide submit button for approvers
					frm.page.clear_primary_action();
					console.log("Debug - Submit button hidden for approver:", frappe.session.user);
				} else {
					console.log("Debug - Submit button kept for applicant:", frappe.session.user);
				}
			});
		}
	},

	ensure_approval_chain: function (frm) {
		// Ensure approval chain is populated when document is loaded
		// DISABLED: This was causing infinite loops
		// Approval chain will be set up automatically during document submission
		/*
		if (!frm.is_new() && frm.doc.docstatus === 0 && (!frm.doc.approval_chain || frm.doc.approval_chain.length === 0)) {
			// Auto-setup approval chain
			frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.setup_approval_chain_for_document",
				args: {
					name: frm.doc.name,
				},
				callback: function (r) {
					if (r.message) {
						frm.reload_doc();
					}
				},
			});
		}
		*/
		
		// Also trigger button setup after a short delay to ensure approval chain is loaded
		setTimeout(function() {
			frm.trigger("setup_approval_buttons");
		}, 1000);
		
	},
	
	setup_approval_buttons: function (frm) {
		// Add refresh approvers button for testing
		if (frm.doc.employee && frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Refresh Approvers"), function () {
				frm.trigger("populate_approvers");
			}, __("Actions"));
		}
		
		// Don't clear custom buttons to preserve debug buttons
		// frm.page.clear_custom_actions();
		
		// Check if current user is in the approvers table and has New status (Material Request style)
		let is_current_approver = false;
		if (frm.doc.approvers && frm.doc.approvers.length > 0) {
			for (let approver of frm.doc.approvers) {
				if (approver.approver === frappe.session.user && approver.status === "New") {
					// If respect_approver_order is enabled, check if this is the first "New" approver
					if (frm.doc.respect_approver_order) {
						let is_first_new_approver = true;
						for (let i = 0; i < frm.doc.approvers.indexOf(approver); i++) {
							if (frm.doc.approvers[i].status === "New") {
								is_first_new_approver = false;
								break;
							}
						}
						if (is_first_new_approver) {
							is_current_approver = true;
						}
					} else {
						is_current_approver = true;
					}
					break;
				}
			}
		}
		
		console.log("Debug - Is Current Approver:", is_current_approver);
		console.log("Debug - Status:", frm.doc.status);
		console.log("Debug - Docstatus:", frm.doc.docstatus);
		console.log("Debug - Session User:", frappe.session.user);
		console.log("Debug - Approvers Table:", frm.doc.approvers);
		console.log("Debug - Respect Approver Order:", frm.doc.respect_approver_order);
		
		// Material Request style approval - only for submitted documents
		if (frm.doc.docstatus === 1 && is_current_approver && frm.doc.status === "Pending Approval") {
			
			frm.add_custom_button(__("Approve"), function () {
				frappe.call({
					method: "hrms.hr.doctype.leave_application.leave_application.approve_reject",
					args: {
						doc: frm.doc.name,
						action: "1"  // 1 = Approve, 0 = Reject
					},
					callback: function (r) {
						if (!r.exc) {
							frm.reload_doc();
						}
					},
				});
			}, "Actions");

			frm.add_custom_button(__("Reject"), function () {
				frappe.call({
					method: "hrms.hr.doctype.leave_application.leave_application.approve_reject",
					args: {
						doc: frm.doc.name,
						action: "0"  // 1 = Approve, 0 = Reject
					},
					callback: function (r) {
						if (!r.exc) {
							frm.reload_doc();
						}
					},
				});
			}, "Actions");
		}
	},

	async set_employee(frm) {
		if (frm.doc.employee) return;

		const employee = await hrms.get_current_employee(frm);
		if (employee) {
			frm.set_value("employee", employee);
		}
	},

	employee: function (frm) {
		console.log(`Employee changed to: ${frm.doc.employee}`);
		frm.trigger("make_dashboard");
		frm.trigger("get_leave_balance");
		frm.trigger("set_leave_approver");
		frm.trigger("populate_approvers");
	},

	populate_approvers: function(frm) {
		// Auto-populate approvers when employee is selected - ALWAYS update when employee changes
		if (frm.doc.employee) {
			// Call the backend to populate approvers based on employee's approval chain
			frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.populate_approvers_from_chain",
				args: {
					employee: frm.doc.employee
				},
				callback: function(r) {
					if (r.message && r.message.approvers) {
						// Always clear existing approvers and repopulate (for employee changes)
						frm.clear_table("approvers");
						
						// Add approvers from the approval chain
						r.message.approvers.forEach(function(approver) {
							frm.add_child("approvers", {
								approver: approver,
								status: "New"
							});
						});
						
						// Set respect_approver_order to checked
						frm.set_value("respect_approver_order", 1);
						
						// Set leave_approver to first approver for email notifications
						if (r.message.approvers.length > 0) {
							frm.set_value("leave_approver", r.message.approvers[0]);
							console.log(`Set leave_approver to first approver: ${r.message.approvers[0]}`);
						}
						
						frm.refresh_field("approvers");
						frm.refresh_field("respect_approver_order");
						frm.refresh_field("leave_approver");
						
						console.log(`Approvers updated for employee ${frm.doc.employee}:`, r.message.approvers);
					}
				}
			});
		}
	},

	leave_approver: function (frm) {
		if (frm.doc.leave_approver) {
			frm.set_value("leave_approver_name", frappe.user.full_name(frm.doc.leave_approver));
		}
	},

	leave_type: function (frm) {
		frm.trigger("get_leave_balance");
	},

	half_day: function (frm) {
		if (frm.doc.half_day) {
			if (frm.doc.from_date == frm.doc.to_date) {
				frm.set_value("half_day_date", frm.doc.from_date);
			} else {
				frm.trigger("half_day_datepicker");
			}
		} else {
			frm.set_value("half_day_date", "");
		}
		frm.trigger("calculate_total_days");
	},

	from_date: function (frm) {
		frm.events.validate_from_to_date(frm, "from_date");
		frm.trigger("make_dashboard");
		frm.trigger("half_day_datepicker");
		frm.trigger("calculate_total_days");
	},

	to_date: function (frm) {
		frm.events.validate_from_to_date(frm, "to_date");
		frm.trigger("make_dashboard");
		frm.trigger("half_day_datepicker");
		frm.trigger("calculate_total_days");
	},

	half_day_date(frm) {
		frm.trigger("calculate_total_days");
	},

	validate_from_to_date: function (frm, updated_field) {
		if (!frm.doc.from_date || !frm.doc.to_date) return;

		const from_date = Date.parse(frm.doc.from_date);
		const to_date = Date.parse(frm.doc.to_date);

		if (to_date < from_date) {
			const other_field = updated_field === "from_date" ? "to_date" : "from_date";

			frm.set_value(other_field, frm.doc[updated_field]);
			frappe.show_alert({
				message: __("Changing '{0}' to {1}.", [
					__(frm.fields_dict[other_field].df.label),
					frappe.datetime.str_to_user(frm.doc[updated_field]),
				]),
				indicator: "blue",
			});
		}
	},

	half_day_datepicker: function (frm) {
		frm.set_value("half_day_date", "");
		if (!(frm.doc.half_day && frm.doc.from_date && frm.doc.to_date)) return;

		const half_day_datepicker = frm.fields_dict.half_day_date.datepicker;
		half_day_datepicker.update({
			minDate: frappe.datetime.str_to_obj(frm.doc.from_date),
			maxDate: frappe.datetime.str_to_obj(frm.doc.to_date),
		});
	},

	get_leave_balance: function (frm) {
		if (
			frm.doc.docstatus === 0 &&
			frm.doc.employee &&
			frm.doc.leave_type &&
			frm.doc.from_date &&
			frm.doc.to_date
		) {
			return frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.get_leave_balance_on",
				args: {
					employee: frm.doc.employee,
					date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					leave_type: frm.doc.leave_type,
					consider_all_leaves_in_the_allocation_period: 1,
				},
				callback: function (r) {
					if (!r.exc && r.message) {
						frm.set_value("leave_balance", r.message);
					} else {
						frm.set_value("leave_balance", "0");
					}
				},
			});
		}
	},

	calculate_total_days: function (frm) {
		if (frm.doc.from_date && frm.doc.to_date && frm.doc.employee && frm.doc.leave_type) {
			// server call is done to include holidays in leave days calculations
			return frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.get_number_of_leave_days",
				args: {
					employee: frm.doc.employee,
					leave_type: frm.doc.leave_type,
					from_date: frm.doc.from_date,
					to_date: frm.doc.to_date,
					half_day: frm.doc.half_day,
					half_day_date: frm.doc.half_day_date,
				},
				callback: function (r) {
					if (r && r.message) {
						frm.set_value("total_leave_days", r.message);
						frm.trigger("get_leave_balance");
					}
				},
			});
		}
	},

	set_leave_approver: function (frm) {
		if (frm.doc.employee) {
			return frappe.call({
				method: "hrms.hr.doctype.leave_application.leave_application.get_leave_approver",
				args: {
					employee: frm.doc.employee,
				},
				callback: function (r) {
					if (r && r.message) {
						frm.set_value("leave_approver", r.message);
					}
				},
			});
		}
	},

	set_form_buttons: async function (frm) {
		let self_approval_not_allowed = frm.doc.__onload
			? frm.doc.__onload.self_leave_approval_not_allowed
			: 0;
		let current_employee = await hrms.get_current_employee();
		if (
			frm.doc.docstatus === 0 &&
			!frm.is_dirty() &&
			!frappe.model.has_workflow(frm.doctype)
		) {
			if (self_approval_not_allowed && current_employee == frm.doc.employee) {
				frm.set_df_property("status", "read_only", 1);
				frm.trigger("show_save_button");
			}
		}
	},
	show_save_button: function (frm) {
		frm.page.set_primary_action("Save", () => {
			frm.save();
		});
		$(".form-message").prop("hidden", true);
	},

	setup_approval_chain: function (frm) {
		// Call the backend to setup the approval chain
		frappe.call({
			method: "hrms.hr.doctype.leave_application.leave_application.setup_approval_chain_for_document",
			args: {
				name: frm.doc.name
			},
			callback: function (r) {
				if (!r.exc) {
					frm.reload_doc();
				}
			}
		});
	},

	populate_approval_chain: function (frm) {
		// Call the backend to populate the approval chain
		frappe.call({
			method: "hrms.hr.doctype.leave_application.leave_application.populate_approval_chain_table",
			args: {
				name: frm.doc.name
			},
			callback: function (r) {
				if (!r.exc) {
					frm.reload_doc();
				}
			}
		});
	},

});

frappe.tour["Leave Application"] = [
	{
		fieldname: "employee",
		title: "Employee",
		description: __("Select the Employee."),
	},
	{
		fieldname: "leave_type",
		title: "Leave Type",
		description: __(
			"Select type of leave the employee wants to apply for, like Sick Leave, Privilege Leave, Casual Leave, etc.",
		),
	},
	{
		fieldname: "from_date",
		title: "From Date",
		description: __("Select the start date for your Leave Application."),
	},
	{
		fieldname: "to_date",
		title: "To Date",
		description: __("Select the end date for your Leave Application."),
	},
	{
		fieldname: "half_day",
		title: "Half Day",
		description: __("To apply for a Half Day check 'Half Day' and select the Half Day Date"),
	},
	{
		fieldname: "leave_approver",
		title: "Leave Approver",
		description: __(
			"Select your Leave Approver i.e. the person who approves or rejects your leaves.",
		),
	},
];
