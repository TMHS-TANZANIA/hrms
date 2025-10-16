# Leave Approval Hierarchy Implementation

## Overview
This implementation adds a multi-level approval system for leave applications based on employee department and role, as discussed in the meeting.

## Approval Hierarchy

### 1. HR Department Employees (including Administration Officers)
- **Approval Chain**: HR Manager → Managing Director
- **Levels**: 2 levels

### 2. Officers from Other Departments  
- **Approval Chain**: Department Manager → HR Manager → Managing Director
- **Levels**: 3 levels

### 3. Managers (any department, but not HR Manager)
- **Approval Chain**: HR Manager → Managing Director  
- **Levels**: 2 levels

### 4. HR Manager
- **Approval Chain**: Managing Director only
- **Levels**: 1 level

## Implementation Details

### New Fields Added to Leave Application
- `approval_level`: Current approval level (integer)
- `current_approver`: Current approver in the chain (User link)
- `approval_chain`: Table showing complete approval chain (Leave Approval Chain child table)

### New Child DocType: Leave Approval Chain
- `approval_level`: Level number (1, 2, 3, etc.)
- `approver`: User who needs to approve at this level
- `approver_name`: Full name of the approver
- `status`: Pending/Approved/Rejected
- `approval_date`: When the approval was given
- `comments`: Comments from the approver

### Key Functions

#### `get_leave_approval_chain(employee)`
Determines the complete approval chain based on employee's department and designation.

#### `setup_approval_chain()`
Sets up the approval chain when a new leave application is created.

#### `approve_application(name, comments=None)`
Approves a leave application at the current level and moves to the next level if applicable.

#### `reject_application(name, reason, comments=None)`
Rejects a leave application (rejects the entire application regardless of level).

### Helper Functions
- `get_hr_manager()`: Finds HR Manager user
- `get_managing_director()`: Finds Managing Director user
- `get_department_manager(department)`: Finds department manager
- `is_hr_employee(department, designation)`: Checks if employee is from HR
- `is_administration_employee(department)`: Checks if employee is from Administration
- `is_manager(designation)`: Checks if employee is a manager

## User Interface Changes

### Leave Application Form
- New "Approval Details" section showing:
  - Current approval level
  - Current approver
  - Complete approval chain table

### Approval Buttons
- Approve/Reject buttons only show for the current approver
- Approve button includes optional comments field
- Reject button includes reason (required) and comments (optional)

## Backward Compatibility
- The original `leave_approver` field is maintained for backward compatibility
- Existing leave applications will continue to work
- New applications will use the multi-level system

## Configuration
The system automatically detects:
- HR Manager: Users with "HR Manager" role
- Managing Director: Users with "Managing Director", "Director", "CEO", or "General Manager" roles
- Department Managers: From Department Approver settings or employees with manager designations

## Testing
The implementation has been tested with various employee types:
- HR Manager (1-level approval: MD only)
- HR Department employees including Administration officers (2-level approval: HR Manager → MD)  
- Managers (2-level approval: HR Manager → MD)
- Regular officers (3-level approval: Department Manager → HR Manager → MD)

## Usage
1. Employee creates a leave application
2. System automatically sets up the approval chain based on employee's department/role
3. First approver receives notification and can approve/reject
4. If approved, application moves to next level approver
5. Process continues until all levels are approved or any level rejects
6. Final approval allows the leave application to be submitted
