# Leave Approval Hierarchy Implementation

## Overview
This implementation uses a **reports_to hierarchy-based system** for leave application approvals. The approval chain automatically follows the employee's reporting structure upward, then ensures HR Manager and Managing Director are included.

## Approval Chain Logic

### Algorithm

The system builds the approval chain using the following steps:

1. **Get the applying employee's user_id** (critical for preventing self-approval)

2. **Follow `reports_to` chain upward** from the employee
   - Start with the employee applying for leave
   - Get their `reports_to` field (their direct manager)
   - Add that manager's `user_id` to the approval chain **ONLY IF** it's not the applying employee
   - Move to that manager and repeat
   - Continue until no more `reports_to` exists (reached top of hierarchy)

3. **Add HR Manager** if not already in the chain
   - Look for users with "HR Manager" role
   - If HR Manager is not already in the chain, add them **ONLY IF** they are not the applying employee
   - If HR Manager is already in the chain (from step 2), skip to avoid duplicates

4. **Add Managing Director at the end** if not already in the chain
   - Look for users with "Managing Director" role  
   - If MD is not already in the chain, add them at the end **ONLY IF** they are not the applying employee
   - If MD is already in the chain (from step 2), skip to avoid duplicates
   - **MD always comes last** in the final chain

5. **Self-Approval Prevention** (CRITICAL)
   - At every step, the system checks if the person being added is the same as the applying employee
   - This ensures that no employee can approve their own leave
   - Examples:
     - MD applying for leave: MD is excluded from chain, goes to HR Manager only
     - HR Manager applying: HR Manager excluded, goes to MD only
     - Regular employee: No self-approval possible

### Safety Features

- **Circular Reference Protection**: Uses a `visited` set to detect circular reports_to chains
- **Maximum Iteration Limit**: Maximum 20 levels to prevent infinite loops
- **Missing User ID Handling**: Skips employees without `user_id` and continues up the chain
- **Self-Approval Prevention**: Excludes applying employee from approval chain at all stages
- **Detailed Logging**: Comprehensive error logs for debugging


## Examples

### Example 1: Regular Employee (3-Level Chain)

**Employee Structure**:
```
Employee A (Sales Officer)
  ↓ reports_to
Employee B (Sales Manager)  
  ↓ reports_to
Employee C (Sales Director)
  ↓ (no more reports_to)
```

**Approval Chain**:
1. Employee B (from reports_to)
2. Employee C (from reports_to)
3. HR Manager (added - not in chain)
4. MD (added - not in chain)

**Result**: `B → C → HR Manager → MD` (4 approvers)

---

### Example 2: HR Department Employee

**Employee Structure**:
```
Employee X (HR Officer)
  ↓ reports_to
HR Manager
  ↓ reports_to  
Managing Director
  ↓ (no more reports_to)
```

**Approval Chain**:
1. HR Manager (from reports_to)
2. MD (from reports_to)
3. HR Manager check: Already in chain at position 1, skip
4. MD check: Already in chain at position 2, skip

**Result**: `HR Manager → MD` (2 approvers, no duplicates)

---

### Example 3: Managing Director Applies for Leave

**Employee Structure**:
```
MD (John - user: john@company.com)
  ↓ reports_to: None
```

**Approval Chain**:
1. reports_to chain: Empty
2. HR Manager check: alice@company.com (not in chain, not same as applicant)
   - Add HR Manager: alice@company.com ✓
3. MD check: john@company.com - **SKIPPED** (same as applying employee)

**Result**: `HR Manager` (1 approver)

> **Self-Approval Prevention**: MD is excluded from their own approval chain.

---

### Example 4: HR Manager Applies for Leave

**Employee Structure**:
```
HR Manager (Alice - user: alice@company.com)
  ↓ reports_to: MD (John - john@company.com)
```

**Approval Chain**:
1. reports_to: MD (john@company.com) - Add ✓
2. MD has no reports_to
3. HR Manager check: alice@company.com - **SKIPPED** (same as applying employee)
4. MD check: Already in chain

**Result**: `MD` (1 approver)

> **Self-Approval Prevention**: HR Manager is excluded from their own approval chain.

---

### Example 5: Employee with No reports_to

**Employee Structure**:
```
Employee Z (Contractor / CEO)
  ↓ reports_to: None
```

**Approval Chain**:
1. No reports_to, skip step 1
2. HR Manager (added)
3. MD (added)

**Result**: `HR Manager → MD` (2 approvers)

---

## Key Functions

### `get_leave_approval_chain(employee)`

**Location**: `hrms/hr/doctype/leave_application/leave_application.py` (Line ~1509)

**Purpose**: Builds the complete approval chain for an employee

**Parameters**:
- `employee` (str): Employee ID

**Returns**:
- `list`: List of user IDs representing the approval chain

---

## Configuration Requirements

### 1. Employee Setup

Each employee (except top-level) should have:
- **`reports_to`**: Link to their direct manager (Employee field)
- **`user_id`**: Link to their User account

**Important**: Managers in the approval chain MUST have a `user_id` set.

### 2. Role Assignment

Two critical roles must be assigned:

| Role | Assigned To | Purpose |
|------|-------------|---------|
| **HR Manager** | HR Manager user(s) | Always included in approval chain |
| **Managing Director** | MD/CEO user | Always last in approval chain |

**Setup Path**: Desk → Users → [User] → Roles

---

## Testing

### Test Script

A comprehensive test script is available at:
```
/home/spectre/frappe/tmhs-dev/apps/hrms/test_approval_chain.py
```

**Run the tests**:
```bash
cd /home/spectre/frappe/tmhs-dev
bench --site hrms.local console
```

Then in the console:
```python
exec(open('/home/spectre/frappe/tmhs-dev/apps/hrms/test_approval_chain.py').read())
test_approval_chain()
```

---

## Debugging

### Error Logs

All approval chain building is logged to Error Log:

**View logs**:
- Desk → Tools → Error Log
- Filter by: `Approval Chain Debug`, `Approval Chain Final`, or `Approval Chain Error`

---

*Last Updated: February 9, 2026*
