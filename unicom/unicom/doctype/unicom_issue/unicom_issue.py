import frappe
from frappe.model.document import Document

class UniComIssue(Document):
    def validate(self):
        # All writes, including administrator writes, go through the workflow API.
        if not self.flags.unicom_api:
            frappe.throw('Use the UniCom workflow to change issues', frappe.PermissionError)

    def on_trash(self):
        frappe.throw('UniCom issues cannot be deleted', frappe.PermissionError)
