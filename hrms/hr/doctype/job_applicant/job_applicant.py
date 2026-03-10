# Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
# License: GNU General Public License v3. See license.txt

# For license information, please see license.txt


import frappe
from frappe import _
from frappe.model.document import Document
from frappe.model.naming import append_number_if_name_exists
from frappe.utils import flt, formatdate, get_url_to_form, validate_email_address

from hrms.hr.doctype.interview.interview import get_interviewers


class DuplicationError(frappe.ValidationError):
	pass


class JobApplicant(Document):
	def onload(self):
		job_offer = frappe.get_all("Job Offer", filters={"job_applicant": self.name})
		if job_offer:
			self.get("__onload").job_offer = job_offer[0].name

	def autoname(self):
		self.name = self.email_id

		# applicant can apply more than once for a different job title or reapply
		if frappe.db.exists("Job Applicant", self.name):
			self.name = append_number_if_name_exists("Job Applicant", self.name)

	def validate(self):
		if self.email_id:
			validate_email_address(self.email_id, True)

		if self.employee_referral:
			self.set_status_for_employee_referral()

		if not self.applicant_name and self.email_id:
			guess = self.email_id.split("@")[0]
			self.applicant_name = " ".join([p.capitalize() for p in guess.split(".")])

	def before_insert(self):
		if self.job_title:
			job_opening_status = frappe.db.get_value("Job Opening", self.job_title, "status")
			if job_opening_status == "Closed":
				frappe.throw(
					_("Cannot create a Job Applicant against a closed Job Opening"), title=_("Not Allowed")
				)

	def set_status_for_employee_referral(self):
		emp_ref = frappe.get_doc("Employee Referral", self.employee_referral)
		if self.status in ["Open", "Replied", "Hold"]:
			emp_ref.db_set("status", "In Process")
		elif self.status in ["Accepted", "Rejected"]:
			emp_ref.db_set("status", self.status)


@frappe.whitelist()
def create_interview(doc, interview_round):
	import json

	if isinstance(doc, str):
		doc = json.loads(doc)
		doc = frappe.get_doc(doc)

	round_designation = frappe.db.get_value("Interview Round", interview_round, "designation")

	if round_designation and doc.designation and round_designation != doc.designation:
		frappe.throw(
			_("Interview Round {0} is only applicable for the Designation {1}").format(
				interview_round, round_designation
			)
		)

	interview = frappe.new_doc("Interview")
	interview.interview_round = interview_round
	interview.job_applicant = doc.name
	interview.designation = doc.designation
	interview.resume_link = doc.resume_link
	interview.job_opening = doc.job_title

	interviewers = get_interviewers(interview_round)
	for d in interviewers:
		interview.append("interview_details", {"interviewer": d.interviewer})

	return interview


@frappe.whitelist()
def get_interview_details(job_applicant):
	interview_details = frappe.db.get_all(
		"Interview",
		filters={"job_applicant": job_applicant, "docstatus": ["!=", 2]},
		fields=["name", "interview_round", "scheduled_on", "average_rating", "status"],
	)
	interview_detail_map = {}
	meta = frappe.get_meta("Interview")
	number_of_stars = meta.get_options("average_rating") or 5

	for detail in interview_details:
		detail.average_rating = detail.average_rating * number_of_stars if detail.average_rating else 0

		interview_detail_map[detail.name] = detail

	return {"interviews": interview_detail_map, "stars": number_of_stars}


@frappe.whitelist()
def get_applicant_to_hire_percentage():
	total_applicants = frappe.db.count("Job Applicant")
	total_hired = frappe.db.count("Job Applicant", filters={"status": "Accepted"})

	return {
		"value": flt(total_hired) / flt(total_applicants) * 100 if total_applicants else 0,
		"fieldtype": "Percent",
	}


@frappe.whitelist()
def send_shortlist_emails(
	applicant_names,
	interview_date,
	interview_time=None,
	interview_round=None,
	interview_location=None,
	custom_message=None,
):
	"""
	Send interview shortlist/invitation emails to a list of Job Applicants.
	Updates each applicant's status to 'Replied' on success.

	Returns a dict: { sent: int, failed: int, errors: list[str] }
	"""
	import json

	if isinstance(applicant_names, str):
		applicant_names = json.loads(applicant_names)

	sent = 0
	failed = 0
	errors = []

	# Format the interview date nicely
	formatted_date = formatdate(interview_date)
	time_str = f" at {interview_time}" if interview_time else ""
	location_str = interview_location or "To be communicated"
	round_str = interview_round or "Interview"
	custom_block = (
		f"""
		<tr>
			<td style="padding:10px 0;border-bottom:1px solid #f0f0f0;color:#757575;">Additional Note</td>
			<td style="padding:10px 0;border-bottom:1px solid #f0f0f0;text-align:right;color:#212121;font-style:italic;">
				{frappe.utils.escape_html(custom_message)}
			</td>
		</tr>
		"""
		if custom_message
		else ""
	)

	for applicant_name in applicant_names:
		try:
			applicant = frappe.db.get_value(
				"Job Applicant",
				applicant_name,
				["applicant_name", "email_id", "job_title"],
				as_dict=True,
			)

			if not applicant or not applicant.email_id:
				failed += 1
				errors.append(f"{applicant_name}: No email address found")
				continue

			job_opening_name = applicant.job_title
			if job_opening_name:
				job_title = frappe.db.get_value("Job Opening", job_opening_name, "job_title") or job_opening_name
			else:
				job_title = "the position"

			subject = _("Congratulations! You've Been Shortlisted for an Interview — {0}").format(
				job_title
			)

			logo_url = frappe.utils.get_url("/files/TMHS-GROUP-LOGO(1)d4a401ec2fbf56a77d.jpg")

			message = f"""
<div style="font-family:'Inter',Arial,sans-serif;max-width:620px;margin:auto;border:1px solid #e0e0e0;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.06);">

	<!-- Logo Header -->
	<div style="background:white;padding:24px 30px;text-align:center;">
		<img src="{logo_url}" alt="TMHS GROUP" style="max-height:60px;width:auto;display:block;margin:0 auto;">
	</div>

	<!-- Header -->
	<div style="background:linear-gradient(135deg,#1a73e8 0%,#0d47a1 100%);padding:36px 30px;text-align:center;color:white;">
		<h2 style="margin:0;font-size:26px;font-weight:700;letter-spacing:-0.5px;">Interview Invitation</h2>
		<p style="margin:10px 0 0 0;opacity:0.9;font-size:15px;">
			You have been shortlisted for <strong>{frappe.utils.escape_html(job_title)}</strong>
		</p>
	</div>

	<!-- Body -->
	<div style="padding:32px 30px;background:white;">
		<p style="font-size:16px;color:#212121;margin-bottom:20px;">
			Dear <strong>{frappe.utils.escape_html(applicant.applicant_name)}</strong>,
		</p>
		<p style="font-size:15px;line-height:1.7;color:#616161;">
			We are pleased to inform you that after reviewing your application, you have been shortlisted
			for an interview for the position of <strong>{frappe.utils.escape_html(job_title)}</strong>.
		</p>

		<!-- Details Table -->
		<div style="background:#f8f9fa;border-radius:10px;padding:20px;margin:24px 0;">
			<h4 style="margin:0 0 16px 0;color:#1a73e8;font-size:13px;text-transform:uppercase;letter-spacing:1px;">
				Interview Details
			</h4>
			<table style="width:100%;border-collapse:collapse;font-size:14px;">
				<tr>
					<td style="padding:10px 0;border-bottom:1px solid #e9ecef;color:#757575;">Interview Round</td>
					<td style="padding:10px 0;border-bottom:1px solid #e9ecef;text-align:right;color:#212121;font-weight:600;">
						{frappe.utils.escape_html(round_str)}
					</td>
				</tr>
				<tr>
					<td style="padding:10px 0;border-bottom:1px solid #e9ecef;color:#757575;">Date &amp; Time</td>
					<td style="padding:10px 0;border-bottom:1px solid #e9ecef;text-align:right;color:#212121;font-weight:600;">
						{formatted_date}{time_str}
					</td>
				</tr>
				<tr>
					<td style="padding:10px 0;border-bottom:1px solid #e9ecef;color:#757575;">Venue / Location</td>
					<td style="padding:10px 0;border-bottom:1px solid #e9ecef;text-align:right;color:#212121;font-weight:600;">
						{frappe.utils.escape_html(location_str)}
					</td>
				</tr>
				{custom_block}
			</table>
		</div>

		<p style="font-size:14px;color:#616161;line-height:1.7;">
			Please confirm your availability by replying to this email.
			If you are unable to attend at the scheduled time, kindly let us know as soon as possible
			so we can make alternative arrangements.
		</p>
	</div>

	<!-- Footer -->
	<div style="background:#f8f9fa;padding:20px 30px;text-align:center;color:#9e9e9e;font-size:12px;border-top:1px solid #f0f0f0;">
		This is an automated message from the HR Management System. Please do not reply directly to this email.
	</div>
</div>
"""

			frappe.sendmail(
				recipients=[applicant.email_id],
				subject=subject,
				message=message,
				now=True,
			)

			# Mark applicant as Replied
			frappe.db.set_value("Job Applicant", applicant_name, "status", "Replied")
			sent += 1

		except Exception as e:
			failed += 1
			errors.append(f"{applicant_name}: {str(e)}")
			frappe.log_error(
				f"Failed to send shortlist email to {applicant_name}: {str(e)}",
				"Shortlist Email Error",
			)

	if sent:
		frappe.db.commit()

	return {"sent": sent, "failed": failed, "errors": errors}

