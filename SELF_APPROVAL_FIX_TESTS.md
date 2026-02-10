# Self-Approval Fix Test Cases

## 🐛 Bug Fixed

**Issue**: MD and HR Manager were being added to their own approval chains, allowing self-approval.

**Solution**: Added logic to exclude the applying employee's `user_id` from the approval chain at all stages.

---

## ✅ Test Scenarios

### Scenario 1: Managing Director Applies for Leave

**Before Fix**:
```
MD Employee (John - user: john@company.com)
  ↓ reports_to: None
Approval Chain: [MD: john@company.com]  ❌ Self-approval!
```

**After Fix**:
```
MD Employee (John - user: john@company.com)
  ↓ reports_to: None
  ↓ Check reports_to chain: Empty
  ↓ Add HR Manager: alice@company.com ✓
  ↓ Add MD: john@company.com - SKIPPED (same as applicant)
Approval Chain: [HR Manager: alice@company.com]  ✓ Correct
```

**Result**: MD's leave is approved by HR Manager only, not by MD themselves.

---

### Scenario 2: HR Manager Applies for Leave

**Before Fix**:
```
HR Manager (Alice - user: alice@company.com)
  ↓ reports_to: MD (john@company.com)
Approval Chain: [MD: john@company.com, HR Manager: alice@company.com]  ❌ Self-approval!
```

**After Fix**:
```
HR Manager (Alice - user: alice@company.com)
  ↓ reports_to: MD (john@company.com)
  ↓ Add MD from reports_to: john@company.com ✓
  ↓ Check if HR Manager needed: alice@company.com - SKIPPED (same as applicant)
  ↓ MD already in chain
Approval Chain: [MD: john@company.com]  ✓ Correct
```

**Result**: HR Manager's leave is approved by MD only, not by HR Manager themselves.

---

### Scenario 3: Regular Employee

**Before & After** (No change - this already worked correctly):
```
Employee Bob (user: bob@company.com)
  ↓ reports_to: Manager Carol (carol@company.com)
  ↓ Manager Carol reports_to: Director Dave (dave@company.com)
  ↓ Director Dave reports_to: None

Approval Chain:
  1. carol@company.com (from reports_to)
  2. dave@company.com (from reports_to)
  3. alice@company.com (HR Manager - not in chain yet)
  4. john@company.com (MD - not in chain yet)

Final: [carol, dave, alice, john]  ✓ Correct
```

---

### Scenario 4: MD Reports to Themselves (Circular Edge Case)

**Before Fix**:
```
MD (John) has reports_to = John (misconfiguration)
Approval Chain: [john@company.com]  ❌ Self-approval through reports_to
```

**After Fix**:
```
MD (John - user: john@company.com)
  ↓ reports_to: John (circular)
  ↓ Detect circular reference, skip
  ↓ Try add HR Manager: alice@company.com ✓
  ↓ Try add MD: john@company.com - SKIPPED (same as applicant)
Approval Chain: [alice@company.com]  ✓ Correct
```

---

### Scenario 5: HR Manager is Also MD (Dual Role)

**Setup**:
```
Alice has both roles:
- HR Manager role
- Managing Director role
```

**After Fix**:
```
Alice applies for leave (user: alice@company.com)
  ↓ reports_to: None
  ↓ Check reports_to chain: Empty
  ↓ Add HR Manager: alice@company.com - SKIPPED (same as applicant)
  ↓ Add MD: alice@company.com - SKIPPED (same as applicant)
Approval Chain: []  ⚠️ EMPTY - needs manual handling or escalation
```

**Note**: This edge case needs special handling - perhaps require Board approval or higher authority.

---

## 🔍 Code Changes Summary

### Three Critical Checks Added

1. **In reports_to chain loop** (Line ~1564):
   ```python
   if reports_to_user != applying_employee_user_id:
       approval_chain.append(reports_to_user)
   else:
       # Skip - prevents self-approval
   ```

2. **When adding HR Manager** (Line ~1590):
   ```python
   if hr_manager != applying_employee_user_id:
       approval_chain.append(hr_manager)
   else:
       # Skip - prevents self-approval
   ```

3. **When adding MD** (Line ~1605):
   ```python
   if md != applying_employee_user_id:
       approval_chain.append(md)
   else:
       # Skip - prevents self-approval
   ```

---

## 🧪 Manual Testing Instructions

### Test 1: MD Leave Application

```bash
# In Frappe console
bench --site hrms.local console
```

```python
# Get MD employee ID
md_user = frappe.db.sql("""
    SELECT u.name, e.name as emp_id
    FROM `tabUser` u
    JOIN `tabHas Role` r ON u.name = r.parent
    JOIN `tabEmployee` e ON u.name = e.user_id
    WHERE r.role = 'Managing Director' AND u.enabled = 1
    LIMIT 1
""", as_dict=True)[0]

print(f"MD User: {md_user.name}, Employee: {md_user.emp_id}")

# Test approval chain
from hrms.hr.doctype.leave_application.leave_application import get_leave_approval_chain
chain = get_leave_approval_chain(md_user.emp_id)

print(f"Approval Chain: {chain}")
print(f"MD in chain? {md_user.name in chain}")  # Should be FALSE
```

### Test 2: HR Manager Leave Application

```python
# Get HR Manager employee ID
hr_user = frappe.db.sql("""
    SELECT u.name, e.name as emp_id
    FROM `tabUser` u
    JOIN `tabHas Role` r ON u.name = r.parent
    JOIN `tabEmployee` e ON u.name = e.user_id
    WHERE r.role = 'HR Manager' AND u.enabled = 1
    LIMIT 1
""", as_dict=True)[0]

print(f"HR Manager User: {hr_user.name}, Employee: {hr_user.emp_id}")

# Test approval chain
chain = get_leave_approval_chain(hr_user.emp_id)

print(f"Approval Chain: {chain}")
print(f"HR Manager in chain? {hr_user.name in chain}")  # Should be FALSE
```

### Test 3: Create Actual Leave Application

```python
# Create leave application for MD
leave_app = frappe.get_doc({
    "doctype": "Leave Application",
    "employee": md_user.emp_id,
    "leave_type": "Casual Leave",
    "from_date": "2026-02-15",
    "to_date": "2026-02-16",
    "description": "Test MD leave"
})
leave_app.insert()

# Check approvers table
for approver in leave_app.approvers:
    print(f"Approver: {approver.approver}")

# Verify MD is NOT in approvers
assert md_user.name not in [a.approver for a in leave_app.approvers], "MD should not be in approvers!"
print("✓ Test passed: MD not in their own approval chain")
```

---

## 📝 Updated Documentation

The fix ensures:
- ✅ No employee can approve their own leave
- ✅ MD's leave goes to HR Manager only
- ✅ HR Manager's leave goes to MD only
- ✅ Regular employees unaffected
- ✅ Circular references handled gracefully

---

*Fix implemented: February 10, 2026*
