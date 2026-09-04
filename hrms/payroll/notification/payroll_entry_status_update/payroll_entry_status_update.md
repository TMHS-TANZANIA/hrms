<p>Hello,</p>

<p>{{ _("The Payroll Entry you raised has moved to") }} <b>{{ doc.workflow_state }}</b>.</p>

<table style="border-collapse: collapse; width: 100%; margin: 15px 0;">
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold; width: 40%;">{{ _("Payroll Entry") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.name }}</td>
  </tr>
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{{ _("Company") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.company }}</td>
  </tr>
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{{ _("Payroll Period") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.start_date }} to {{ doc.end_date }}</td>
  </tr>
  <tr>
    <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">{{ _("Status") }}</td>
    <td style="padding: 8px; border: 1px solid #ddd;">{{ doc.workflow_state }}</td>
  </tr>
</table>

<p style="margin: 25px 0;">
  <a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}" style="background-color: #1b66ec; color: #ffffff; padding: 10px 20px; text-decoration: none; border-radius: 4px; font-weight: bold; display: inline-block;">
    {{ _("Open Payroll Entry") }}
  </a>
</p>

<p>{{ _("If the button doesn't work, copy and paste this link into your browser:") }}<br>
<span style="color: #555;">{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}</span></p>
