# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

"""Self-check for the Payroll Entry approval reminders, run with the bench python,

	env/bin/python apps/hrms/hrms/payroll/test_approval_reminders.py

No site needed - the queries and the mail call are stubbed and we assert on what the
job decided to send.
"""

import datetime

from frappe import _dict

from hrms.payroll.doctype.payroll_entry import payroll_entry as pe

NOW = datetime.datetime(2026, 9, 4, 18, 0, 0)

WORKFLOW_STATES = ["Draft", "Waiting for HR Review", "Waiting for Director", "Approved", "Rejected"]


def action(name, state, hours_ago):
	return _dict(
		name=name,
		reference_name=f"PE-{name}",
		workflow_state=state,
		creation=NOW - datetime.timedelta(hours=hours_ago),
	)


ACTIONS = [
	action("a", "Waiting for HR Review", 2),  # due
	action("b", "Waiting for HR Review", 3),  # between milestones
	action("c", "Waiting for Director", 12),  # due
	action("d", "Waiting for Director", 13),  # past the last milestone
	action("e", "Draft", 8),  # not submitted for approval yet
]


def main():
	sent = []

	def get_all(doctype, **kwargs):
		if doctype == "Workflow Document State":
			return WORKFLOW_STATES
		if doctype == "Workflow Action":
			states = dict(kwargs["filters"])["workflow_state"][1]
			return [a for a in ACTIONS if a.workflow_state in states]
		if doctype == "Workflow Action Permitted Role":
			return ["Managing Director"]
		raise AssertionError(f"unexpected query on {doctype}")

	pe.now_datetime = lambda: NOW
	pe.get_workflow_name = lambda doctype: "PAYROLL-T"
	pe.get_users_with_role = lambda role: ["md@example.com"]
	pe.frappe.get_all = get_all
	pe.frappe.get_doc = lambda doctype, name=None: _dict(
		doctype=doctype, name=name, as_dict=lambda: {"name": name}, subject="{{ name }}", response_html="x", response=""
	)
	pe.frappe.render_template = lambda template, context: template.replace("{{ name }}", str(context["name"]))
	pe.frappe.sendmail = lambda **kwargs: sent.append(kwargs)
	pe._ = lambda msg: msg

	# the draft state is dropped, every state an entry only reaches after submission is kept
	assert pe.get_pending_approval_states() == set(WORKFLOW_STATES[1:]), "draft must not be chased"

	pe.send_approval_reminders()

	assert [m["reference_name"] for m in sent] == ["PE-a", "PE-c"], (
		f"only the entries sitting on a milestone are chased, got {[m['reference_name'] for m in sent]}"
	)
	assert sent[0]["subject"] == "Reminder (2h): PE-a"
	assert sent[1]["subject"] == "Reminder (12h): PE-c"
	assert sent[0]["recipients"] == ["md@example.com"]

	print("approval reminders ok")


if __name__ == "__main__":
	main()
