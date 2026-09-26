<p>Hello,</p>

<p>{{ _("{0} has reviewed and approved this Bulk Salary Assignment. The Salary Structure Assignments are being created, and the Payroll Entry can be made from it.").format(frappe.get_fullname(frappe.session.user)) }}</p>

<table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold; width: 40%;">{{ _("Reference") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.name }}</td>
  </tr>
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{{ _("Title") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.title or '-' }}</td>
  </tr>
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{{ _("Company") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.company }}</td>
  </tr>
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{{ _("Employees") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.employees | length }}</td>
  </tr>
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{{ _("Prepared By") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ frappe.get_fullname(doc.owner) }}</td>
  </tr>
</table>

<p style="margin: 25px 0;">
  <a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}" style="background-color: #1b66ec; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">
    {{ _("Open Bulk Salary Assignment") }}
  </a>
</p>

<p>{{ _("If the button doesn't work, copy and paste this link into your browser:") }}<br>
<span style="color: #555;">{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}</span></p>
