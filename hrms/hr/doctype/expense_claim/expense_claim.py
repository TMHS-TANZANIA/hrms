# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt


import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.model.workflow import get_workflow_name
from frappe.query_builder.functions import Sum
from frappe.utils import cstr, flt, get_link_to_form

import erpnext
from erpnext.accounts.doctype.repost_accounting_ledger.repost_accounting_ledger import (
	validate_docs_for_voucher_types,
)
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.accounts.general_ledger import make_gl_entries
from erpnext.controllers.accounts_controller import AccountsController

import hrms
from hrms.hr.utils import set_employee_name, share_doc_with_approver, validate_active_employee
from hrms.mixins.pwa_notifications import PWANotificationsMixin


class InvalidExpenseApproverError(frappe.ValidationError):
	pass


class ExpenseApproverIdentityError(frappe.ValidationError):
	pass


class MismatchError(frappe.ValidationError):
	pass


class ExpenseClaim(AccountsController, PWANotificationsMixin):
	def onload(self):
		self.get("__onload").make_payment_via_journal_entry = frappe.db.get_single_value(
			"Accounts Settings", "make_payment_via_journal_entry"
		)
		self.set_onload(
			"self_expense_approval_not_allowed",
			frappe.db.get_single_value("HR Settings", "prevent_self_expense_approval"),
		)

	def after_insert(self):
		self.notify_approver()

	def validate(self):
		validate_active_employee(self.employee)
		set_employee_name(self)
		self.validate_sanctioned_amount()
		self.calculate_total_amount()
		self.validate_advances()
		self.set_expense_account(validate=True)
		self.calculate_taxes()
		self.validate_manager_has_not_been_removed()
		self.set_status()
		self.validate_company_and_department()
		if self.task and not self.project:
			self.project = frappe.db.get_value("Task", self.task, "project")

	def set_status(self, update=False):
		status = {"0": "Draft", "1": "Submitted", "2": "Cancelled"}[cstr(self.docstatus or 0)]

		precision = self.precision("grand_total")

		if self.docstatus == 1:
			if self.approval_status == "Approved":
				if (
					# set as paid
					self.is_paid
					or (
						flt(self.total_sanctioned_amount) > 0
						and (
							# grand total is reimbursed
							(flt(self.grand_total, precision) == flt(self.total_amount_reimbursed, precision))
							# grand total (to be paid) is 0 since linked advances already cover the claimed amount
							or (flt(self.grand_total, precision) == 0)
						)
					)
				):
					status = "Paid"
				elif flt(self.total_sanctioned_amount) > 0:
					status = "Unpaid"
				else:
					status = "Approved"
			elif self.approval_status == "Rejected":
				status = "Rejected"
			else:
				status = "Pending"

		if update:
			self.db_set("status", status)
			self.publish_update()
			self.notify_update()
		else:
			self.status = status

	def validate_company_and_department(self):
		if self.department:
			company = frappe.db.get_value("Department", self.department, "company")
			if company and self.company != company:
				frappe.throw(
					_("Department {0} does not belong to company: {1}").format(self.department, self.company),
					exc=MismatchError,
				)

	def validate_for_self_approval(self):
		self_expense_approval_not_allowed = frappe.db.get_single_value(
			"HR Settings", "prevent_self_expense_approval"
		)
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id")
		if (
			self_expense_approval_not_allowed
			and employee_user == frappe.session.user
			and not get_workflow_name("Expense Claim")
		):
			frappe.throw(_("Self-approval for Expense Claims is not allowed"))

	def on_update(self):
		if self.expense_approver:
			share_doc_with_approver(self, self.expense_approver)

		for approver in self.approvers:
			if approver.approver:
				share_doc_with_approver(self, approver.approver)

		self.publish_update()
		self.notify_approval_status()

	def after_delete(self):
		self.publish_update()

	def before_submit(self):
		if not self.payable_account and not self.is_paid:
			frappe.throw(_("Payable Account is mandatory to submit an Expense Claim"))

		self.validate_for_self_approval()

	def publish_update(self):
		employee_user = frappe.db.get_value("Employee", self.employee, "user_id", cache=True)
		hrms.refetch_resource("hrms:my_claims", employee_user)
		hrms.refetch_resource("hrms:team_claims")

	def on_submit(self):
		self.update_task_and_project()
		self.make_gl_entries()
		self.send_for_approval()

		update_reimbursed_amount(self)

		self.update_claimed_amount_in_employee_advance()
		self.set_status(update=True)

	def on_update_after_submit(self):
		if self.check_if_fields_updated([], {"taxes": ("account_head",), "expenses": ()}):
			validate_docs_for_voucher_types(["Expense Claim"])
			self.repost_accounting_entries()

	def on_cancel(self):
		self.update_task_and_project()
		self.ignore_linked_doctypes = ("GL Entry", "Stock Ledger Entry", "Payment Ledger Entry")
		if self.payable_account:
			self.make_gl_entries(cancel=True)

		update_reimbursed_amount(self)

		self.update_claimed_amount_in_employee_advance()
		self.publish_update()

	def update_claimed_amount_in_employee_advance(self):
		for d in self.get("advances"):
			frappe.get_doc("Employee Advance", d.employee_advance).update_claimed_amount()

	def validate_manager_has_not_been_removed(self):
		# Remove empty rows
		approvers = [row for row in self.approvers if row.approver]

		# Identify the requester's manager
		manager_user_account = get_manager_for_proposal_approval(self.employee)

		if manager_user_account:
			found_the_manager = False
			for approver in approvers:
				if approver.approver == manager_user_account:
					found_the_manager = True
					break

			if not found_the_manager:
				approvers.append(frappe._dict({"approver": manager_user_account, "status": "New"}))
				frappe.msgprint(_("You can't remove your manager"), alert=True)

		self.set("approvers", approvers)

		if len(self.approvers) < 2:
			frappe.throw(_("Please add at least two approvers."))

	def get_pending_approvers(self):
		"""Get list of approvers with 'New' status"""
		pending_approvers = []
		for approver in self.approvers:
			if approver.status == "New":
				pending_approvers.append(approver.approver)
		return pending_approvers

	def send_for_approval(self):
		from frappe.utils import get_url

		doc = self
		approver_emails = []

		for row in doc.approvers:
			if row.status == "New" and row.approver:
				email = frappe.db.get_value("User", row.approver, "email")
				if email:
					approver_emails.append(email)

		if not approver_emails:
			return

		doc_url = get_url(f"/app/expense-claim/{doc.name}")
		subject = f"Approval Required: Expense Claim {doc.name} - {doc.employee_name}"

		message = f"""
			<p>Hello,</p>
			<p>
				The Expense Claim <b>{doc.name}</b> for <b>{doc.employee_name}</b> has been submitted and requires your review.
			</p>
			<p>
				<a href="{doc_url}"
				style="
						background-color:#1f8ceb;
						color:#ffffff;
						padding:10px 16px;
						text-decoration:none;
						border-radius:4px;
						display:inline-block;
				">
					Review Expense Claim
				</a>
			</p>
			<p>Thank you.</p>
		"""

		frappe.sendmail(
			recipients=approver_emails,
			subject=subject,
			message=message,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			now=True,
		)

	def update_task_and_project(self):
		if self.task:
			task = frappe.get_doc("Task", self.task)

			ExpenseClaim = frappe.qb.DocType("Expense Claim")
			task.total_expense_claim = (
				frappe.qb.from_(ExpenseClaim)
				.select(Sum(ExpenseClaim.total_sanctioned_amount))
				.where(
					(ExpenseClaim.docstatus == 1)
					& (ExpenseClaim.project == self.project)
					& (ExpenseClaim.task == self.task)
				)
			).run()[0][0]

			task.save()
		elif self.project:
			frappe.get_doc("Project", self.project).update_project()

	def make_gl_entries(self, cancel=False):
		if flt(self.total_sanctioned_amount) > 0:
			gl_entries = self.get_gl_entries()
			make_gl_entries(gl_entries, cancel)

	def get_gl_entries(self):
		gl_entry = []
		self.validate_account_details()

		# payable entry
		if self.grand_total:
			gl_entry.append(
				self.get_gl_dict(
					{
						"account": self.payable_account,
						"credit": self.grand_total,
						"credit_in_account_currency": self.grand_total,
						"against": ",".join([d.default_account for d in self.expenses]),
						"party_type": "Employee",
						"party": self.employee,
						"against_voucher_type": self.doctype,
						"against_voucher": self.name,
						"cost_center": self.cost_center,
						"project": self.project,
					},
					item=self,
				)
			)

		# expense entries
		for data in self.expenses:
			gl_entry.append(
				self.get_gl_dict(
					{
						"account": data.default_account,
						"debit": data.sanctioned_amount,
						"debit_in_account_currency": data.sanctioned_amount,
						"against": self.employee,
						"cost_center": data.cost_center or self.cost_center,
						"project": data.project or self.project,
					},
					item=data,
				)
			)

		for data in self.advances:
			gl_entry.append(
				self.get_gl_dict(
					{
						"account": data.advance_account,
						"credit": data.allocated_amount,
						"credit_in_account_currency": data.allocated_amount,
						"against": ",".join([d.default_account for d in self.expenses]),
						"party_type": "Employee",
						"party": self.employee,
						"against_voucher_type": "Employee Advance",
						"against_voucher": data.employee_advance,
					}
				)
			)

		self.add_tax_gl_entries(gl_entry)

		if self.is_paid and self.grand_total:
			# payment entry
			payment_account = get_bank_cash_account(self.mode_of_payment, self.company).get("account")
			gl_entry.append(
				self.get_gl_dict(
					{
						"account": payment_account,
						"credit": self.grand_total,
						"credit_in_account_currency": self.grand_total,
						"against": self.employee,
					},
					item=self,
				)
			)

			gl_entry.append(
				self.get_gl_dict(
					{
						"account": self.payable_account,
						"party_type": "Employee",
						"party": self.employee,
						"against": payment_account,
						"debit": self.grand_total,
						"debit_in_account_currency": self.grand_total,
						"against_voucher": self.name,
						"against_voucher_type": self.doctype,
					},
					item=self,
				)
			)

		return gl_entry

	def add_tax_gl_entries(self, gl_entries):
		# tax table gl entries
		for tax in self.get("taxes"):
			gl_entries.append(
				self.get_gl_dict(
					{
						"account": tax.account_head,
						"debit": tax.tax_amount,
						"debit_in_account_currency": tax.tax_amount,
						"against": self.employee,
						"cost_center": tax.cost_center or self.cost_center,
						"project": tax.project or self.project,
						"against_voucher_type": self.doctype,
						"against_voucher": self.name,
					},
					item=tax,
				)
			)

	def validate_account_details(self):
		for data in self.expenses:
			if not data.cost_center:
				frappe.throw(
					_("Row {0}: {1} is required in the expenses table to book an expense claim.").format(
						data.idx, frappe.bold(_("Cost Center"))
					)
				)

		if self.is_paid:
			if not self.mode_of_payment:
				frappe.throw(_("Mode of payment is required to make a payment").format(self.employee))

	def calculate_total_amount(self):
		self.total_claimed_amount = 0
		self.total_sanctioned_amount = 0

		for d in self.get("expenses"):
			self.round_floats_in(d)

			if self.approval_status == "Rejected":
				d.sanctioned_amount = 0.0

			self.total_claimed_amount += flt(d.amount)
			self.total_sanctioned_amount += flt(d.sanctioned_amount)

		self.round_floats_in(self, ["total_claimed_amount", "total_sanctioned_amount"])

	@frappe.whitelist()
	def calculate_taxes(self):
		self.total_taxes_and_charges = 0
		for tax in self.taxes:
			self.round_floats_in(tax)

			if tax.rate:
				tax.tax_amount = flt(
					flt(self.total_sanctioned_amount) * flt(flt(tax.rate) / 100),
					tax.precision("tax_amount"),
				)

			tax.total = flt(tax.tax_amount) + flt(self.total_sanctioned_amount)
			self.total_taxes_and_charges += flt(tax.tax_amount)

		self.round_floats_in(self, ["total_taxes_and_charges"])

		self.grand_total = (
			flt(self.total_sanctioned_amount)
			+ flt(self.total_taxes_and_charges)
			- flt(self.total_advance_amount)
		)
		self.round_floats_in(self, ["grand_total"])

	def validate_advances(self):
		self.total_advance_amount = 0
		precision = self.precision("total_advance_amount")

		for d in self.get("advances"):
			self.round_floats_in(d)

			ref_doc = frappe.db.get_value(
				"Employee Advance",
				d.employee_advance,
				["posting_date", "paid_amount", "claimed_amount", "return_amount", "advance_account"],
				as_dict=1,
			)
			d.posting_date = ref_doc.posting_date
			d.advance_account = ref_doc.advance_account
			d.advance_paid = ref_doc.paid_amount
			d.unclaimed_amount = flt(ref_doc.paid_amount) - flt(ref_doc.claimed_amount)

			if d.allocated_amount and flt(d.allocated_amount) > flt(
				flt(d.unclaimed_amount) - flt(d.return_amount), precision
			):
				frappe.throw(
					_("Row {0}# Allocated amount {1} cannot be greater than unclaimed amount {2}").format(
						d.idx, d.allocated_amount, d.unclaimed_amount
					)
				)

			self.total_advance_amount += flt(d.allocated_amount)

		if self.total_advance_amount:
			self.round_floats_in(self, ["total_advance_amount"])
			amount_with_taxes = flt(
				(flt(self.total_sanctioned_amount, precision) + flt(self.total_taxes_and_charges, precision)),
				precision,
			)

			if flt(self.total_advance_amount, precision) > amount_with_taxes:
				frappe.throw(_("Total advance amount cannot be greater than total sanctioned amount"))

	def validate_sanctioned_amount(self):
		for d in self.get("expenses"):
			if flt(d.sanctioned_amount) > flt(d.amount):
				frappe.throw(
					_("Sanctioned Amount cannot be greater than Claim Amount in Row {0}.").format(d.idx)
				)

	def set_expense_account(self, validate=False):
		for expense in self.expenses:
			if not expense.default_account or not validate:
				expense.default_account = get_expense_claim_account(expense.expense_type, self.company)[
					"account"
				]


def update_reimbursed_amount(doc):
	total_amount_reimbursed = get_total_reimbursed_amount(doc)

	doc.total_amount_reimbursed = total_amount_reimbursed
	frappe.db.set_value("Expense Claim", doc.name, "total_amount_reimbursed", total_amount_reimbursed)

	doc.set_status(update=True)


def get_total_reimbursed_amount(doc):
	if doc.is_paid:
		# No need to check for cancelled state here as it will anyways update status as cancelled
		return doc.grand_total
	else:
		JournalEntryAccount = frappe.qb.DocType("Journal Entry Account")
		amount_via_jv = (
			frappe.qb.from_(JournalEntryAccount)
			.select(Sum(JournalEntryAccount.debit_in_account_currency - JournalEntryAccount.credit_in_account_currency))
			.where((JournalEntryAccount.reference_name == doc.name) & (JournalEntryAccount.docstatus == 1))
		).run()[0][0] or 0

		PaymentEntryReference = frappe.qb.DocType("Payment Entry Reference")
		amount_via_payment_entry = (
			frappe.qb.from_(PaymentEntryReference)
			.select(Sum(PaymentEntryReference.allocated_amount))
			.where((PaymentEntryReference.reference_name == doc.name) & (PaymentEntryReference.docstatus == 1))
		).run()[0][0] or 0

		return flt(amount_via_jv) + flt(amount_via_payment_entry)


def get_outstanding_amount_for_claim(claim):
	precision = frappe.get_precision("Expense Claim", "grand_total")

	if isinstance(claim, str):
		claim = frappe.db.get_value(
			"Expense Claim",
			claim,
			(
				"total_sanctioned_amount",
				"total_taxes_and_charges",
				"total_amount_reimbursed",
				"total_advance_amount",
			),
			as_dict=True,
		)

	outstanding_amt = (
		flt(claim.total_sanctioned_amount)
		+ flt(claim.total_taxes_and_charges)
		- flt(claim.total_amount_reimbursed)
		- flt(claim.total_advance_amount)
	)

	return flt(outstanding_amt, precision)


@frappe.whitelist()
def make_bank_entry(dt, dn):
	from erpnext.accounts.doctype.journal_entry.journal_entry import get_default_bank_cash_account

	expense_claim = frappe.get_doc(dt, dn)
	default_bank_cash_account = get_default_bank_cash_account(expense_claim.company, "Bank")
	if not default_bank_cash_account:
		default_bank_cash_account = get_default_bank_cash_account(expense_claim.company, "Cash")

	payable_amount = get_outstanding_amount_for_claim(expense_claim)

	je = frappe.new_doc("Journal Entry")
	je.voucher_type = "Bank Entry"
	je.company = expense_claim.company
	je.remark = "Payment against Expense Claim: " + dn

	je.append(
		"accounts",
		{
			"account": expense_claim.payable_account,
			"debit_in_account_currency": payable_amount,
			"reference_type": "Expense Claim",
			"party_type": "Employee",
			"party": expense_claim.employee,
			"cost_center": erpnext.get_default_cost_center(expense_claim.company),
			"reference_name": expense_claim.name,
		},
	)

	je.append(
		"accounts",
		{
			"account": default_bank_cash_account.account,
			"credit_in_account_currency": payable_amount,
			"balance": default_bank_cash_account.balance,
			"account_currency": default_bank_cash_account.account_currency,
			"cost_center": erpnext.get_default_cost_center(expense_claim.company),
			"account_type": default_bank_cash_account.account_type,
		},
	)

	return je.as_dict()


@frappe.whitelist()
def get_expense_claim_account_and_cost_center(expense_claim_type, company):
	data = get_expense_claim_account(expense_claim_type, company)
	cost_center = erpnext.get_default_cost_center(company)

	return {"account": data.get("account"), "cost_center": cost_center}


@frappe.whitelist()
def get_expense_claim_account(expense_claim_type, company):
	account = frappe.db.get_value(
		"Expense Claim Account", {"parent": expense_claim_type, "company": company}, "default_account"
	)
	if not account:
		frappe.throw(
			_("Set the default account for the {0} {1}").format(
				frappe.bold(_("Expense Claim Type")),
				get_link_to_form("Expense Claim Type", expense_claim_type),
			)
		)

	return {"account": account}


@frappe.whitelist()
def get_advances(employee, advance_id=None):
	advance = frappe.qb.DocType("Employee Advance")

	query = frappe.qb.from_(advance).select(
		advance.name,
		advance.purpose,
		advance.posting_date,
		advance.paid_amount,
		advance.claimed_amount,
		advance.return_amount,
		advance.advance_account,
	)

	if not advance_id:
		query = query.where(
			(advance.docstatus == 1)
			& (advance.employee == employee)
			& (advance.paid_amount > 0)
			& (advance.status.notin(["Claimed", "Returned", "Partly Claimed and Returned"]))
		)
	else:
		query = query.where(advance.name == advance_id)

	return query.run(as_dict=True)


@frappe.whitelist()
def get_expense_claim(
	employee_name, company, employee_advance_name, posting_date, paid_amount, claimed_amount, return_amount
):
	default_payable_account = frappe.get_cached_value(
		"Company", company, "default_expense_claim_payable_account"
	)
	default_cost_center = frappe.get_cached_value("Company", company, "cost_center")

	expense_claim = frappe.new_doc("Expense Claim")
	expense_claim.company = company
	expense_claim.employee = employee_name
	expense_claim.payable_account = default_payable_account
	expense_claim.cost_center = default_cost_center
	expense_claim.is_paid = 1 if flt(paid_amount) else 0
	expense_claim.append(
		"advances",
		{
			"employee_advance": employee_advance_name,
			"posting_date": posting_date,
			"advance_paid": flt(paid_amount),
			"unclaimed_amount": flt(paid_amount) - flt(claimed_amount),
			"allocated_amount": get_allocation_amount(
				paid_amount=(paid_amount), claimed_amount=(claimed_amount), return_amount=(return_amount)
			),
			"return_amount": flt(return_amount),
		},
	)

	return expense_claim


def update_payment_for_expense_claim(doc, method=None):
	"""
	Updates payment/reimbursed amount in Expense Claim
	on Payment Entry/Journal Entry cancellation/submission
	"""
	if doc.doctype == "Payment Entry" and not (doc.payment_type == "Pay" and doc.party):
		return

	payment_table = "accounts" if doc.doctype == "Journal Entry" else "references"
	doctype_field = "reference_type" if doc.doctype == "Journal Entry" else "reference_doctype"

	for d in doc.get(payment_table):
		if d.get(doctype_field) == "Expense Claim" and d.reference_name:
			expense_claim = frappe.get_doc("Expense Claim", d.reference_name)
			update_reimbursed_amount(expense_claim)

			if doc.doctype == "Payment Entry":
				update_outstanding_amount_in_payment_entry(expense_claim, d.name)


def update_outstanding_amount_in_payment_entry(expense_claim: dict, pe_reference: str):
	"""updates outstanding amount back in Payment Entry reference"""
	# TODO: refactor convoluted code after erpnext payment entry becomes extensible
	outstanding_amount = get_outstanding_amount_for_claim(expense_claim)
	frappe.db.set_value("Payment Entry Reference", pe_reference, "outstanding_amount", outstanding_amount)


def validate_expense_claim_in_jv(doc, method=None):
	"""Validates Expense Claim amount in Journal Entry"""
	for d in doc.accounts:
		if d.reference_type == "Expense Claim":
			outstanding_amt = get_outstanding_amount_for_claim(d.reference_name)
			if d.debit > outstanding_amt:
				frappe.throw(
					_(
						"Row No {0}: Amount cannot be greater than the Outstanding Amount against Expense Claim {1}. Outstanding Amount is {2}"
					).format(d.idx, d.reference_name, outstanding_amt)
				)


@frappe.whitelist()
def make_expense_claim_for_delivery_trip(source_name, target_doc=None):
	doc = get_mapped_doc(
		"Delivery Trip",
		source_name,
		{"Delivery Trip": {"doctype": "Expense Claim", "field_map": {"name": "delivery_trip"}}},
		target_doc,
	)

	return doc


@frappe.whitelist()
def approve_reject(doc, action):
	doc = frappe.get_doc("Expense Claim", doc)
	if doc.docstatus != 1:
		frappe.msgprint(_("Expense Claim must be submitted before approval"), alert=True, indicator="Red")
		return

	if doc.status in ["Rejected", "Approved"]:
		frappe.msgprint(_("No Action Needed"), alert=True, indicator="Yellow")
		return

	try:
		user_found = False
		for approver in doc.approvers:
			if approver.approver == frappe.session.user and approver.status == "New":
				user_found = True
				i = doc.approvers.index(approver)
				for approver_ in doc.approvers:
					j = doc.approvers.index(approver_)
					if approver_.status == "New" and i > j and doc.respect_approver_order:
						frappe.msgprint(
							_("Please wait for " + approver_.approver + " to complete their approval process"),
							alert=True,
							indicator="Red",
						)
						return
				if str(action) == "1":
					approver.status = "Approved"
				else:
					approver.status = "Rejected"
				doc.save()
				frappe.db.commit()
				frappe.msgprint(
					_("Expense Claim has been Approved" if str(action) == "1" else "Expense Claim has been Rejected"),
					alert=True,
					indicator="Green" if str(action) == "1" else "red",
				)
				break
		if not user_found:
			frappe.msgprint(
				_(
					"You're not allowed to perform this action. If you think this is a mistake, send an email to IT for further assistance."
				),
				alert=True,
				indicator="Red",
			)
			return

		# Update the status field
		approved = sum(1 for a in doc.approvers if a.status == "Approved")
		rejected = sum(1 for a in doc.approvers if a.status == "Rejected")

		if approved == len(doc.approvers):
			doc.db_set("approval_status", "Approved")
			doc.set_status(update=True)
			doc.save()
			frappe.db.commit()
		elif rejected > 0:
			doc.db_set("approval_status", "Rejected")
			doc.set_status(update=True)
			doc.save()
			frappe.db.commit()

	except Exception as _e:
		_approve_reject = "Approve" if str(action) == "1" else "Reject"
		frappe.msgprint(_("Failed to {0}. Try again. Error: {1}").format(_approve_reject, _e), alert=True)


@frappe.whitelist()
def get_manager_for_proposal_approval(employee):
	manager_employee_record = frappe.get_value("Employee", employee, "reports_to")
	if not manager_employee_record:
		return None
	return frappe.get_value("Employee", manager_employee_record, "user_id")


@frappe.whitelist()
def get_allocation_amount(paid_amount=None, claimed_amount=None, return_amount=None, unclaimed_amount=None):
	if unclaimed_amount is not None and return_amount is not None:
		return flt(unclaimed_amount) - flt(return_amount)
	elif paid_amount is not None and claimed_amount is not None and return_amount is not None:
		return flt(paid_amount) - (flt(claimed_amount) + flt(return_amount))
	else:
		frappe.throw(_("Invalid parameters provided. Please pass the required arguments."))
