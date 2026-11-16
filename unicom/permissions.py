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


def file_permission(doc, user=None, ptype=None, debug=False):
    if doc.attached_to_doctype != 'UniCom Issue' or not doc.attached_to_name:
        return True
    if not doc.is_private:
        return False
    try:
        issue = frappe.get_doc('UniCom Issue', doc.attached_to_name)
    except frappe.DoesNotExistError:
        return False
    return issue_permission(issue, user=user, ptype='read' if ptype in (None, 'read', 'select') else ptype)
