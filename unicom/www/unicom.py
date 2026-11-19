import frappe

def get_context(context):
    if frappe.session.user == 'Guest':
        frappe.local.flags.redirect_location = '/login?redirect-to=/unicom'
        raise frappe.Redirect
    context.no_cache = 1
    context.csrf_token = frappe.sessions.get_csrf_token()
    configured = frappe.db.get_single_value('System Settings', 'date_format')
    context.date_format = configured if configured in ('yyyy-mm-dd', 'dd-mm-yyyy', 'dd/mm/yyyy', 'dd.mm.yyyy', 'mm/dd/yyyy', 'mm-dd-yyyy') else 'yyyy-mm-dd'
