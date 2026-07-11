<div align="center">
	<a href="https://frappe.io/hr">
		<img src=".github/frappe-hr-logo.png" height="80px" width="80px" alt="Frappe HR Logo">
	</a>
	<h2>Frappe HR</h2>
	<p align="center">
		<p>Open Source, modern, and easy-to-use HR and Payroll Software</p>
	</p>

[![CI](https://github.com/frappe/hrms/actions/workflows/ci.yml/badge.svg?branch=develop)](https://github.com/frappe/hrms/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/frappe/hrms/branch/develop/graph/badge.svg?token=0TwvyUg3I5)](https://codecov.io/gh/frappe/hrms)

<a href="https://trendshift.io/repositories/10972" target="_blank"><img src="https://trendshift.io/api/badge/repositories/10972" alt="frappe%2Fhrms | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
</div>

<div align="center">
	<img src=".github/hrms-hero.png"/>
</div>

<div align="center">
	<a href="https://frappe.io/hr">Website</a>
	-
	<a href="https://docs.frappe.io/hr/introduction">Documentation</a>
</div>

## Frappe HR

Frappe HR has everything you need to drive excellence within the company. It's a complete HRMS solution with over 13 different modules right from Employee Management, Onboarding, Leaves, to Payroll, Taxation, and more!

## Motivation
When Frappe team started growing in terms of size, we needed an open-source HR and Payroll software. We didn't find any "true" open-source HR software out there and so decided to build one ourselves.
Initially, it was a set of modules within ERPNext but version 14 onwards, as the modules became more mature, Frappe HR was created as a separate product.

## Key Features

- **Employee Lifecycle**: From onboarding employees, managing promotions and transfers, all the way to documenting feedback with exit interviews, make life easier for employees throughout their life cycle.
- **Leave and Attendance**: Configure leave policies, pull regional holidays with a click, check-in and check-out with geolocation capturing, track leave balances and attendance with reports.
- **Expense Claims and Advances**: Manage employee advances, claim expenses, configure multi-level approval workflows, all this with seamless integration with ERPNext accounting.
- **Performance Management**: Track goals, align goals with key result areas (KRAs), enable employees to evaluate themselves, make managing appraisal cycles easy.
- **Payroll & Taxation**: Create salary structures, configure income tax slabs, run standard payroll, accomodate additional salaries and off cycle payments, view income breakup on salary slips and so much more.
- **Frappe HR Mobile App**: Apply for and approve leaves on the go, check-in and check-out, access employee profile right from the mobile app.

<details open>

<summary>View Screenshots</summary>
	<img src=".github/hrms-appraisal.png"/>
	<img src=".github/hrms-requisition.png"/>
	<img src=".github/hrms-attendance.png"/>
	<img src=".github/hrms-salary.png"/>
	<img src=".github/hrms-pwa.png"/>
</details>


### App Versions
```
{
	"erpnext": "16.0.0-dev",
	"frappe": "16.0.0-dev",
	"hrms": "16.0.0-dev"
}
```
### Route
```
Form/Disciplinary Charge/TMHS/CONS/0098-SH
```
### Traceback
```
Traceback (most recent call last):
  File "apps/frappe/frappe/app.py", line 116, in application
    response = frappe.api.handle(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "apps/frappe/frappe/api/__init__.py", line 49, in handle
    data = endpoint(**arguments)
           ^^^^^^^^^^^^^^^^^^^^^
  File "apps/frappe/frappe/api/v1.py", line 36, in handle_rpc_call
    return frappe.handler.handle()
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "apps/frappe/frappe/handler.py", line 51, in handle
    data = execute_cmd(cmd)
           ^^^^^^^^^^^^^^^^
  File "apps/frappe/frappe/handler.py", line 84, in execute_cmd
    return frappe.call(method, **frappe.form_dict)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "apps/frappe/frappe/__init__.py", line 1461, in call
    return fn(*args, **newargs)
           ^^^^^^^^^^^^^^^^^^^^
  File "apps/frappe/frappe/utils/typing_validations.py", line 32, in wrapper
    return func(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^
  File "apps/hrms/hrms/hr/doctype/disciplinary_charge/disciplinary_charge.py", line 90, in make_proceeding_step
    disply_inv = frappe.get_all("Disciplinary Investigation",filters=[["disciplinary_charge",'=',doc.name]])
                                                                                                 ^^^
NameError: name 'doc' is not defined

```
### Request Data
```
{
	"type": "POST",
	"args": {
		"displinary_charge_name": "TMHS/CONS/0098-SH"
	},
	"headers": {},
	"error_handlers": {},
	"url": "/api/method/hrms.hr.doctype.disciplinary_charge.disciplinary_charge.make_proceeding_step",
	"request_id": null
}
```
### Response Data
```
{
	"exception": "NameError: name 'doc' is not defined",
	"exc_type": "NameError",
	"_exc_source": "hrms (app)"
}
```
```