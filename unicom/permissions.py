import frappe


def issue_query(user=None):
    user = user or frappe.session.user
    if user == 'Administrator':
        return ''
    if user == 'Guest':
        return '1=0'
    u = frappe.db.escape(user)
    return f'''(`tabUniCom Issue`.`owner` = {u} OR `tabUniCom Issue`.`accountable_owner` = {u}
        OR EXISTS (SELECT 1 FROM `tabUniCom Issue Access` a
            WHERE a.parent = `tabUniCom Issue`.`name` AND a.parenttype = 'UniCom Issue'
            AND a.parentfield = 'access' AND a.user = {u}))'''


def issue_permission(doc, user=None, ptype=None, debug=False):
    user = user or frappe.session.user
    if user == 'Administrator':
        return True
    if user == 'Guest' or ptype not in (None, 'read', 'select'):
        return False
    return bool(doc.owner == user or doc.accountable_owner == user or any(row.user == user for row in doc.access))



def notification_permission(doc, user=None, ptype=None, debug=False):
    # Controller hooks only restrict native DocType permissions. A truthy return
    # is required to preserve Frappe's existing behavior for other notifications.
    if getattr(doc, 'document_type', None) != 'UniCom Issue':
        return True
    user = user or frappe.session.user
    return user == 'Administrator' or (user != 'Guest' and user == doc.for_user)
