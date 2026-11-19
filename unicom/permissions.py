import frappe
from unicom.access import has_management_access


def issue_action_query(user=None):
    user = user or frappe.session.user
    if not has_management_access(user):
        return '1=0'
    if user == 'Administrator':
        return ''
    if user == 'Guest':
        return '1=0'
    u = frappe.db.escape(user)
    return f'''(`tabUniCom Issue`.`owner` = {u} OR `tabUniCom Issue`.`accountable_owner` = {u}
        OR EXISTS (SELECT 1 FROM `tabUniCom Issue Access` a
            WHERE a.parent = `tabUniCom Issue`.`name` AND a.parenttype = 'UniCom Issue'
            AND a.parentfield = 'access' AND a.user = {u}))'''


def issue_action_permission(doc, user=None):
    user = user or frappe.session.user
    if not has_management_access(user):
        return False
    if user == 'Administrator':
        return True
    if user == 'Guest':
        return False
    return bool(doc.owner == user or doc.accountable_owner == user or any(row.user == user for row in doc.access))



def system_manager(user):
    return user == 'Administrator' or (user != 'Guest' and 'System Manager' in frappe.get_roles(user))


def issue_query(user=None):
    user = user or frappe.session.user
    if not has_management_access(user):
        return '1=0'
    if system_manager(user):
        return ''
    legacy = issue_action_query(user)
    if user == 'Guest':
        return legacy
    return f"({legacy} OR `tabUniCom Issue`.`coordination_user` = {frappe.db.escape(user)})"


def issue_permission(doc, user=None, ptype=None, debug=False):
    user = user or frappe.session.user
    if not has_management_access(user):
        return False
    if user == 'Administrator':
        return True
    if user == 'Guest' or ptype not in (None, 'read', 'select'):
        return False
    return bool(system_manager(user) or issue_action_permission(doc, user) or getattr(doc, 'coordination_user', None) == user)



def notification_permission(doc, user=None, ptype=None, debug=False):
    # Controller hooks only restrict native DocType permissions. A truthy return
    # is required to preserve Frappe's existing behavior for other notifications.
    if getattr(doc, 'document_type', None) != 'UniCom Issue':
        return True
    user = user or frappe.session.user
    return has_management_access(user) and (user == 'Administrator' or user == doc.for_user)


def notification_query(user=None):
    if has_management_access(user or frappe.session.user):
        return ''
    return "IFNULL(`tabNotification Log`.`document_type`, '') != 'UniCom Issue'"
