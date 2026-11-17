import frappe
from frappe.model.document import Document
from unicom.issue_ids import next_issue_id

class UniComIssue(Document):
    def before_insert(self):
        if self.issue_id:
            frappe.throw('Issue ID is assigned automatically', frappe.ValidationError)
        self.issue_id = next_issue_id()

    def validate(self):
        # All writes, including administrator writes, go through the workflow API.
        if not self.flags.unicom_api:
            frappe.throw('Use the UniCom workflow to change issues', frappe.PermissionError)
        previous = self.get_doc_before_save()
        if previous and (previous.reference_doctype != self.reference_doctype or previous.reference_name != self.reference_name):
            frappe.throw('Source document cannot be changed', frappe.ValidationError)
        if previous and previous.issue_id != self.issue_id:
            frappe.throw('Issue ID cannot be changed', frappe.ValidationError)

    def on_trash(self):
        frappe.throw('UniCom issues cannot be deleted', frappe.PermissionError)
