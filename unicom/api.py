"""The only mutation surface for UniCom records; generic document writes are denied."""
import base64
import json
from bs4 import BeautifulSoup

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today
from frappe.utils.file_manager import save_file

STATUSES = ('Open', 'In Progress', 'Waiting', 'Resolved')
CHANNELS = ('Internal Note', 'Call', 'Meeting', 'Email', 'WhatsApp')


def _user():
    if frappe.session.user == 'Guest':
        frappe.throw(_('Please sign in'), frappe.PermissionError)
    return frappe.session.user


def _json(value, fallback):
    if value is None:
        return fallback
    return json.loads(value) if isinstance(value, str) else value


def _users(values):
    values = _json(values, [])
    if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
        frappe.throw(_('Expected a list of users'))
    values = list(dict.fromkeys(values))
    if len(values) > 100:
        frappe.throw(_('Too many users'))
    for user in values:
        if user == 'Guest' or not frappe.db.exists('User', {'name': user, 'enabled': 1}):
            frappe.throw(_('Invalid or disabled user: {0}').format(user))
    return values


def _validate(doc):
    if not (doc.title or '').strip():
        frappe.throw(_('Title is required'))
    _users([doc.accountable_owner])
    if doc.status not in STATUSES:
        frappe.throw(_('Invalid status'))
    if doc.status == 'Resolved':
        if not (doc.resolution_note or '').strip():
            frappe.throw(_('A resolution note is required'))
    elif not (doc.next_action or '').strip() or not doc.next_action_date:
        frappe.throw(_('An active issue needs a next action and date'))
    if doc.next_action_date:
        getdate(doc.next_action_date)


def _set_users(doc, reason, users):
    users = _users(users)
    doc.access = [r for r in doc.access if r.reason != reason or r.user in users]
    existing = {r.user for r in doc.access if r.reason == reason}
    for user in users:
        if user not in existing:
            doc.append('access', {'user': user, 'reason': reason})


def _snapshot(doc):
    return {'title': doc.title, 'description': doc.description, 'accountable_owner': doc.accountable_owner,
            'status': doc.status, 'next_action': doc.next_action, 'next_action_date': str(doc.next_action_date or ''),
            'resolution_note': doc.resolution_note,
            'participants': sorted(r.user for r in doc.access if r.reason == 'Participant'),
            'follow_up_assignees': sorted(r.user for r in doc.access if r.reason == 'Follow-up')}


def _event(doc, kind, before=None, **kwargs):
    after = _snapshot(doc)
    changes = {k: {'from': before.get(k), 'to': v} for k, v in after.items() if before is not None and before.get(k) != v}
    doc.append('timeline', {'kind': kind, 'actor': _user(), 'recorded_at': now_datetime(),
                            'changes': json.dumps(changes, default=str), **kwargs})


def _doc(name, lock=False):
    _user()
    if lock:
        # Serialize updates before fetching, preserving timeline and current action under concurrency.
        frappe.db.sql('SELECT name FROM `tabUniCom Issue` WHERE name=%s FOR UPDATE', name)
    doc = frappe.get_doc('UniCom Issue', name)
    if not frappe.has_permission('UniCom Issue', 'read', doc=doc):
        frappe.throw(_('Not permitted'), frappe.PermissionError)
    return doc


def _output(doc):
    result = doc.as_dict()
    result['overdue'] = bool(doc.status != 'Resolved' and doc.next_action_date and getdate(doc.next_action_date) < getdate(today()))
    result['attachments'] = frappe.get_all('File', filters={'attached_to_doctype': 'UniCom Issue', 'attached_to_name': doc.name, 'is_private': 1}, fields=['name', 'file_name', 'file_url', 'creation'])
    return result


@frappe.whitelist()
def users(query=''):
    _user()
    return frappe.get_all('User', filters={'enabled': 1, 'name': ['not in', ['Guest', 'Administrator']], 'full_name': ['like', '%' + query + '%']}, fields=['name', 'full_name'], order_by='full_name', limit_page_length=10000)


@frappe.whitelist()
def list_issues(view='all', status=None, search=None, start=0, page_length=20):
    user = _user()
    filters = {}
    if status:
        if status not in STATUSES: frappe.throw(_('Invalid status'))
        filters['status'] = status
    if view == 'overdue':
        filters.update({'status': ['!=', 'Resolved'], 'next_action_date': ['<', today()]})
    elif view not in ('all', 'mine'):
        frappe.throw(_('Invalid view'))
    if search:
        filters['title'] = ['like', '%' + search + '%']
    # frappe.get_list applies both role permissions and issue_query.
    rows = frappe.get_list('UniCom Issue', filters=filters, fields=['name', 'title', 'status', 'accountable_owner', 'owner', 'next_action', 'next_action_date', 'modified'], order_by='modified desc', limit_start=max(0, int(start)), limit_page_length=min(100, max(1, int(page_length)))) if view != 'mine' else None
    if view == 'mine':
        # Query filter must be combined with access permissions before pagination.
        u = frappe.db.escape(user)
        filters['name'] = ['in', [r.name for r in frappe.db.sql(f'''SELECT DISTINCT i.name FROM `tabUniCom Issue` i LEFT JOIN `tabUniCom Issue Access` a ON a.parent=i.name AND a.parenttype='UniCom Issue' AND a.parentfield='access' WHERE i.owner={u} OR i.accountable_owner={u} OR (a.user={u} AND a.reason IN ('Participant','Follow-up'))''', as_dict=True)] or ['']]
        rows = frappe.get_list('UniCom Issue', filters=filters, fields=['name','title','status','accountable_owner','owner','next_action','next_action_date','modified'], order_by='modified desc', limit_start=max(0,int(start)), limit_page_length=min(100,max(1,int(page_length))))
    for row in rows:
        row['overdue'] = bool(row.status != 'Resolved' and row.next_action_date and getdate(row.next_action_date) < getdate(today()))
    return rows


@frappe.whitelist()
def get_issue(name):
    return _output(_doc(name))


@frappe.whitelist(methods=['POST'])
def create_issue(title, accountable_owner, next_action, next_action_date, description='', participants=None, follow_up_assignees=None):
    _user()
    doc = frappe.new_doc('UniCom Issue')
    doc.update({'title': title, 'description': frappe.utils.sanitize_html(description or '', always_sanitize=True), 'accountable_owner': accountable_owner, 'status': 'Open', 'next_action': next_action, 'next_action_date': next_action_date})
    _set_users(doc, 'Participant', participants)
    _set_users(doc, 'Follow-up', follow_up_assignees)
    _validate(doc)
    _event(doc, 'Created')
    doc.flags.unicom_api = True
    doc.insert(ignore_permissions=True)
    return _output(doc)


@frappe.whitelist(methods=['POST'])
def update_issue(name, values):
    doc = _doc(name, lock=True)
    before = _snapshot(doc)
    values = _json(values, {})
    if not isinstance(values, dict) or set(values) - {'title','description','accountable_owner','status','next_action','next_action_date','resolution_note','participants','follow_up_assignees'}:
        frappe.throw(_('Invalid fields'))
    for key, val in values.items():
        if key == 'participants': _set_users(doc, 'Participant', val)
        elif key == 'follow_up_assignees': _set_users(doc, 'Follow-up', val)
        elif key == 'description': doc.description = frappe.utils.sanitize_html(val or '', always_sanitize=True)
        else: doc.set(key, val)
    _validate(doc)
    kind = 'Resolved' if before['status'] != 'Resolved' and doc.status == 'Resolved' else 'Reopened' if before['status'] == 'Resolved' and doc.status != 'Resolved' else 'Updated'
    _event(doc, kind, before)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    return _output(doc)


@frappe.whitelist(methods=['POST'])
def log_communication(name, channel, happened_at, body, next_action=None, next_action_date=None, resolution_note=None, contact='', mentions=None):
    doc = _doc(name, lock=True)
    if doc.status == 'Resolved': frappe.throw(_('Reopen the issue first'))
    if channel not in CHANNELS or not happened_at or not (body or '').strip(): frappe.throw(_('Channel, time and outcome are required'))
    before = _snapshot(doc)
    if resolution_note:
        doc.status, doc.resolution_note = 'Resolved', resolution_note
    else:
        doc.next_action, doc.next_action_date = next_action, next_action_date
    # Mention grants are durable and separate from participant membership.
    mentioned_users = [node.get('data-id') for node in BeautifulSoup(body, 'html.parser').select('[data-type=mention][data-id]')]
    for user in _users(mentioned_users):
        if not any(r.user == user and r.reason == 'Mention' for r in doc.access): doc.append('access', {'user': user, 'reason': 'Mention'})
    _validate(doc)
    _event(doc, 'Communication', before, channel=channel, happened_at=happened_at, body=frappe.utils.sanitize_html(body, always_sanitize=True), contact=contact)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    return _output(doc)


@frappe.whitelist(methods=['POST'])
def upload_attachment(name, filename, content):
    _doc(name, lock=True)
    if not filename or '/' in filename or '\\' in filename: frappe.throw(_('Invalid filename'))
    try: data = base64.b64decode(content, validate=True)
    except Exception: frappe.throw(_('Invalid file content'))
    if len(data) > 10 * 1024 * 1024: frappe.throw(_('Maximum attachment size is 10 MB'))
    file = save_file(filename, data, 'UniCom Issue', name, is_private=1)
    return {'name': file.name, 'file_name': file.file_name, 'file_url': file.file_url}
