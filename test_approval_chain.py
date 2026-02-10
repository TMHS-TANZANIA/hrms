"""
Test Script for Reports-To Chain Based Leave Approval

This script tests the new get_leave_approval_chain function to ensure it:
1. Follows reports_to chain upward correctly
2. Adds HR Manager if not already present
3. Adds MD at the end if not already present
4. Has no duplicates
5. MD is always last

Run this in bench console:
    cd /home/spectre/frappe/tmhs-dev
    bench --site hrms.local console
    
Then paste this script and modify employee IDs as needed
"""

import frappe
from hrms.hr.doctype.leave_application.leave_application import get_leave_approval_chain

def test_approval_chain():
    """Test the approval chain for different employee scenarios"""
    
    print("\n" + "="*80)
    print("TESTING REPORTS-TO CHAIN BASED LEAVE APPROVAL")
    print("="*80 + "\n")
    
    # Test 1: Get list of employees to test with
    print("Fetching employees from system...")
    employees = frappe.get_all(
        "Employee",
        filters={"status": "Active"},
        fields=["name", "employee_name", "reports_to", "department", "user_id"],
        limit=10
    )
    
    if not employees:
        print("❌ No active employees found in the system!")
        return
    
    print(f"✅ Found {len(employees)} active employees\n")
    
    # Test each employee
    for emp in employees:
        print("-" * 80)
        print(f"Testing Employee: {emp.name} ({emp.employee_name})")
        print(f"  Department: {emp.department or 'N/A'}")
        print(f"  Reports To: {emp.reports_to or 'None'}")
        print(f"  User ID: {emp.user_id or 'None'}")
        
        # Get approval chain
        chain = get_leave_approval_chain(emp.name)
        
        print(f"\n  Approval Chain ({len(chain)} approvers):")
        if chain:
            for i, approver in enumerate(chain, 1):
                # Get approver name
                approver_name = frappe.db.get_value("User", approver, "full_name") or approver
                # Check if they're HR or MD
                is_hr = frappe.db.exists("Has Role", {"parent": approver, "role": "HR Manager"})
                is_md = frappe.db.exists("Has Role", {"parent": approver, "role": "Managing Director"})
                
                role_info = []
                if is_hr:
                    role_info.append("HR Manager")
                if is_md:
                    role_info.append("MD")
                
                role_str = f" [{', '.join(role_info)}]" if role_info else ""
                print(f"    {i}. {approver_name} ({approver}){role_str}")
        else:
            print("    ⚠️  No approval chain found!")
        
        print()
    
    print("="*80)
    print("TESTING COMPLETE")
    print("="*80)
    print("\nCheck the Error Log for detailed trace of approval chain building:")
    print("  Desk → Tools → Error Log")
    print("  Filter by: 'Approval Chain Debug' or 'Approval Chain Final'")
    print()

def test_specific_employee(employee_id):
    """Test a specific employee's approval chain"""
    print(f"\nTesting specific employee: {employee_id}")
    
    emp = frappe.get_doc("Employee", employee_id)
    print(f"  Employee: {emp.employee_name}")
    print(f"  Department: {emp.department or 'N/A'}")
    print(f"  Reports To: {emp.reports_to or 'None'}")
    
    chain = get_leave_approval_chain(employee_id)
    
    print(f"\nApproval Chain ({len(chain)} approvers):")
    for i, approver in enumerate(chain, 1):
        approver_name = frappe.db.get_value("User", approver, "full_name") or approver
        print(f"  {i}. {approver_name} ({approver})")
    
    return chain

def verify_chain_requirements(employee_id):
    """Verify that the chain meets all requirements"""
    print(f"\n{'='*80}")
    print(f"VERIFYING REQUIREMENTS FOR EMPLOYEE: {employee_id}")
    print(f"{'='*80}\n")
    
    chain = get_leave_approval_chain(employee_id)
    
    # Check 1: No duplicates
    has_duplicates = len(chain) != len(set(chain))
    status_dup = "✅ PASS" if not has_duplicates else "❌ FAIL"
    print(f"{status_dup} - No Duplicates: {not has_duplicates}")
    
    # Check 2: HR Manager is in chain
    hr_manager_users = frappe.get_all(
        "Has Role",
        filters={"role": "HR Manager"},
        fields=["parent"]
    )
    hr_manager_ids = [u.parent for u in hr_manager_users]
    has_hr = any(hr in chain for hr in hr_manager_ids)
    status_hr = "✅ PASS" if has_hr else "⚠️  WARN"
    print(f"{status_hr} - HR Manager in chain: {has_hr}")
    
    # Check 3: MD is in chain
    md_users = frappe.get_all(
        "Has Role",
        filters={"role": "Managing Director"},
        fields=["parent"]
    )
    md_ids = [u.parent for u in md_users]
    has_md = any(md in chain for md in md_ids)
    status_md = "✅ PASS" if has_md else "⚠️  WARN"
    print(f"{status_md} - MD in chain: {has_md}")
    
    # Check 4: MD is last (if present)
    if has_md and chain:
        md_last = chain[-1] in md_ids
        status_last = "✅ PASS" if md_last else "❌ FAIL"
        print(f"{status_last} - MD is last: {md_last}")
    
    # Check 5: Chain follows reports_to
    emp = frappe.get_doc("Employee", employee_id)
    if emp.reports_to:
        reports_to_user = frappe.db.get_value("Employee", emp.reports_to, "user_id")
        if reports_to_user and chain:
            first_is_reports_to = chain[0] == reports_to_user
            status_first = "✅ PASS" if first_is_reports_to else "❌ FAIL"
            print(f"{status_first} - First approver is reports_to: {first_is_reports_to}")
    
    print(f"\n{'='*80}\n")

# Instructions
print("""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    APPROVAL CHAIN TEST SCRIPT LOADED                         ║
╚══════════════════════════════════════════════════════════════════════════════╝

Available Functions:
  1. test_approval_chain()              - Test all active employees
  2. test_specific_employee(emp_id)     - Test a specific employee
  3. verify_chain_requirements(emp_id)   - Verify chain meets all requirements

Example Usage:
  >>> test_approval_chain()
  >>> test_specific_employee("HR-EMP-00001")
  >>> verify_chain_requirements("HR-EMP-00001")

Ready to test!
""")
