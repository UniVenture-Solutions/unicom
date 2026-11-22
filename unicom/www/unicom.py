import frappe
from urllib.parse import urlencode, quote
from unicom.access import require_management_access

def get_context(context):
    if frappe.session.user == 'Guest':
        request = frappe.local.request
        path = request.path
        if path != '/unicom' and not path.startswith('/unicom/'):
            path = '/unicom'
        query = request.query_string.decode('utf-8', errors='replace')
        target = quote(path, safe='/@') + ('?' + query if query else '')
        frappe.local.flags.redirect_location = '/login?' + urlencode({'redirect-to': target})
        raise frappe.Redirect(http_status_code=302)
    require_management_access()
    context.no_cache = 1
    context.csrf_token = frappe.sessions.get_csrf_token()
    configured = frappe.db.get_single_value('System Settings', 'date_format')
    context.date_format = configured if configured in ('yyyy-mm-dd', 'dd-mm-yyyy', 'dd/mm/yyyy', 'dd.mm.yyyy', 'mm/dd/yyyy', 'mm-dd-yyyy') else 'yyyy-mm-dd'
