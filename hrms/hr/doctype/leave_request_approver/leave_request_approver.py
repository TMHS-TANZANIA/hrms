import frappe
from frappe.model.document import Document
 
class LeaveRequestApprover(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        approver: DF.Link
        parent: DF.Data
        parentfield: DF.Data
        parenttype: DF.Data
        status: DF.Literal["New", "Approved", "Rejected"]
    # end: auto-generated types

    pass
