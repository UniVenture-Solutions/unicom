"""One role boundary shared by UniCom entry points and permissions."""
import frappe
from frappe import _


def has_management_access(user=None):
    user = user or frappe.session.user
    return bool(user and user != 'Guest' and 'Management' in frappe.get_roles(user))


def require_management_access(user=None):
    if not has_management_access(user):
        frappe.throw(_('The Management role is required to access UniCom.'), frappe.PermissionError)


def prevent_notification_response_cache(response, request):
    # Native notifications unrelated to UniCom retain Frappe's existing behavior.
    method='frappe.desk.doctype.notification_log.notification_log.get_notification_logs'
    if not request.path.endswith(method):
        return
    payload=response.get_json(silent=True) or {}
    message=payload.get('message') or {}
    if isinstance(message,dict) and any(row.get('document_type')=='UniCom Issue' for row in message.get('notification_logs',[])):
        response.headers['Cache-Control']='no-store, private'
