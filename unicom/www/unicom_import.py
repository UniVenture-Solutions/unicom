import frappe
from unicom.access import require_management_access
from unicom.one_time_import import _host_allowed


def get_context(context):
    context.no_cache = 1
    if not _host_allowed():
        frappe.throw('Page not available.', frappe.PermissionError)
    context.import_authorized = frappe.session.user == 'Administrator'
    if context.import_authorized:
        require_management_access()
        context.csrf_token = frappe.sessions.get_csrf_token()
