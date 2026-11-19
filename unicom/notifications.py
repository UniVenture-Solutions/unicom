"""Recipient-private, in-app-only UniCom mention notifications."""
from html import escape
from urllib.parse import quote

import frappe
from frappe import _
from unicom.access import has_management_access, require_management_access
from frappe.desk.doctype.notification_settings.notification_settings import is_notifications_enabled


def notify_mentions(doc, users, context):
    if not users:
        return
    actor = frappe.session.user
    recipients = [user for user in dict.fromkeys(users) if user != actor and has_management_access(user)]
    if not recipients:
        return
    subjects = {
        'description': _('You were mentioned in the description of {0}'),
        'comment': _('You were mentioned in a comment on {0}'),
        'reply': _('You were mentioned in a reply on {0}'),
    }
    title = escape(f'{getattr(doc, "issue_id", None) or doc.name} — {doc.title}')
    subject = subjects[context].format(title)
    for user in recipients:
        if not is_notifications_enabled(user):
            continue
        # Alert is Frappe's in-app-only type: it never sends notification email.
        # Insert in the issue transaction; native realtime is emitted after commit.
        notification = frappe.new_doc('Notification Log')
        notification.update({'type': 'Alert', 'subject': subject, 'for_user': user,
                             'from_user': actor, 'document_type': 'UniCom Issue',
                             'document_name': doc.name, 'link': '/unicom/' + quote(doc.name, safe='')})
        notification.insert(ignore_permissions=True)


def _filters(user):
    return {'for_user': user, 'document_type': 'UniCom Issue', 'type': 'Alert', 'document_name': ['is', 'set'], 'link': ['like', '/unicom/%']}


def list_for_user(user, start=0, page_length=20):
    require_management_access(user)
    from bs4 import BeautifulSoup
    start = max(0, int(start))
    page_length = min(50, max(1, int(page_length)))
    filters = _filters(user)
    rows = frappe.get_all('Notification Log', filters=filters,
                          fields=['name', 'subject', 'document_name', 'from_user', 'creation', 'read'],
                          order_by='creation desc, name desc', limit_start=start, limit_page_length=page_length + 1)
    items = [{'name': row.name, 'subject': BeautifulSoup(row.subject or '', 'html.parser').get_text(),
              'issue_name': row.document_name, 'link': '/unicom/' + quote(row.document_name, safe=''),
              'from_user': row.from_user, 'creation': row.creation, 'read': bool(row.read)} for row in rows[:page_length]]
    return {'items': items, 'unread_count': frappe.db.count('Notification Log', filters={**filters, 'read': 0}),
            'has_more': len(rows) > page_length, 'next_start': start + len(items)}


def mark_read_for_user(user, name):
    require_management_access(user)
    if not isinstance(name, str) or not name or len(name) > 140:
        frappe.throw(_('Notification not found'), frappe.PermissionError)
    filters = {**_filters(user), 'name': name}
    if not frappe.db.exists('Notification Log', filters):
        frappe.throw(_('Notification not found'), frappe.PermissionError)
    frappe.db.set_value('Notification Log', filters, 'read', 1, update_modified=False)
    return {'name': name, 'read': True}
