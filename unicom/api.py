"""The only mutation surface for UniCom records; generic document writes are denied."""
import io
import json
import os
import secrets
from urllib.parse import urlencode
from PIL import Image, UnidentifiedImageError
from werkzeug.wrappers import Response
from bs4 import BeautifulSoup

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today
from unicom.permissions import issue_permission

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



def _coordination_selection(value, current=None):
    if value is None or (isinstance(value, str) and value == ''):
        return None
    if not isinstance(value, str):
        frappe.throw(_('Coordinating user must be a user ID'))
    if value != current:
        _users([value])
        if frappe.db.get_value('User', value, 'user_type') != 'System User':
            frappe.throw(_('Coordinating user must be an enabled system user'))
    return value


def _image_url(doc, attachment):
    return '/api/method/unicom.api.inline_image?' + urlencode({'name': doc.name, 'attachment': attachment})


def _decoded_image(data):
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in ('PNG', 'JPEG', 'GIF', 'WEBP') or image.width * image.height > 25000000:
                raise ValueError('Unsupported image')
            image.load()
            image = image.convert('RGBA' if 'A' in image.getbands() else 'RGB')
            output = io.BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        frappe.throw(_('Invalid or unsupported image'))


def _rich_html(value, doc=None):
    if not isinstance(value, str):
        frappe.throw(_('Invalid rich text'))
    parsed = BeautifulSoup(value, 'html.parser')
    for node in parsed.find_all(True):
        if node.name in ('video', 'audio', 'source', 'track', 'picture', 'iframe', 'object', 'embed', 'svg', 'math', 'link', 'style') or node.has_attr('srcset') or node.has_attr('poster') or node.has_attr('background') or 'url(' in node.get('style', '').lower():
            frappe.throw(_('Unsupported embedded content'))
        if node.name != 'img' and node.has_attr('src'):
            frappe.throw(_('Unsupported embedded content'))
    attachments = {row.name: row for row in getattr(doc, 'attachments', [])} if doc else {}
    urls = {_image_url(doc, name): row for name, row in attachments.items()} if doc else {}
    for node in parsed.find_all('img'):
        src = node.get('src', '')
        row = urls.get(src)
        if not row:
            frappe.throw(_('Images must be private attachments of this issue'))
        with open(_attachment_path(row.storage_key), 'rb') as source:
            _decoded_image(source.read())
        node.attrs = {'src': _image_url(doc, row.name), 'alt': node.get('alt', '')}
    return frappe.utils.sanitize_html(str(parsed), always_sanitize=True)


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
            'coordination_user': getattr(doc, 'coordination_user', None) or None, 'status': doc.status, 'next_action': doc.next_action, 'next_action_date': str(doc.next_action_date or ''),
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
    if not issue_permission(doc, user=frappe.session.user, ptype='read'):
        frappe.throw(_('Not permitted'), frappe.PermissionError)
    return doc


def _output(doc):
    result = doc.as_dict()
    result['overdue'] = bool(doc.status != 'Resolved' and doc.next_action_date and getdate(doc.next_action_date) < getdate(today()))
    result['attachments'] = [{'name': row.name, 'file_name': row.file_name, 'file_url': '/api/method/unicom.api.download_attachment?' + urlencode({'name': doc.name, 'attachment': row.name}), 'creation': row.uploaded_at} for row in doc.attachments]
    profile_users = {doc.owner, doc.accountable_owner, getattr(doc, 'coordination_user', None)}
    profile_users.update(event.actor for event in doc.timeline if event.actor)
    profile_users.discard(None)
    profile_users.discard('')
    # This document was already checked for access. Only its referenced people are exposed.
    result['user_profiles'] = frappe.get_all('User', filters={'name': ['in', sorted(profile_users)]}, fields=['name', 'full_name', 'user_image'], limit_page_length=0) if profile_users else []
    return result


@frappe.whitelist()
def users(query=''):
    _user()
    return frappe.get_all('User', filters={'enabled': 1, 'name': ['not in', ['Guest', 'Administrator']], 'full_name': ['like', '%' + query + '%']}, fields=['name', 'full_name', 'user_type', 'user_image'], order_by='full_name', limit_page_length=10000)


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
    rows = frappe.get_list('UniCom Issue', filters=filters, fields=['name', 'issue_id', 'title', 'status', 'accountable_owner', 'coordination_user', 'owner', 'next_action', 'next_action_date', 'modified'], order_by='modified desc', limit_start=max(0, int(start)), limit_page_length=min(100, max(1, int(page_length)))) if view != 'mine' else None
    if view == 'mine':
        # Query filter must be combined with access permissions before pagination.
        u = frappe.db.escape(user)
        filters['name'] = ['in', [r.name for r in frappe.db.sql(f'''SELECT DISTINCT i.name FROM `tabUniCom Issue` i LEFT JOIN `tabUniCom Issue Access` a ON a.parent=i.name AND a.parenttype='UniCom Issue' AND a.parentfield='access' WHERE i.owner={u} OR i.accountable_owner={u} OR (a.user={u} AND a.reason IN ('Participant','Follow-up'))''', as_dict=True)] or ['']]
        rows = frappe.get_list('UniCom Issue', filters=filters, fields=['name','issue_id','title','status','accountable_owner','coordination_user','owner','next_action','next_action_date','modified'], order_by='modified desc', limit_start=max(0,int(start)), limit_page_length=min(100,max(1,int(page_length))))
    for row in rows:
        row['overdue'] = bool(row.status != 'Resolved' and row.next_action_date and getdate(row.next_action_date) < getdate(today()))
    return rows


@frappe.whitelist()
def get_issue(name):
    return _output(_doc(name))


@frappe.whitelist(methods=['POST'])
def create_issue(title, accountable_owner, next_action, next_action_date, description='', participants=None, follow_up_assignees=None, coordination_user=None):
    _user()
    doc = frappe.new_doc('UniCom Issue')
    doc.update({'title': title, 'description': _rich_html(description or ''), 'accountable_owner': accountable_owner, 'coordination_user': _coordination_selection(coordination_user), 'status': 'Open', 'next_action': next_action, 'next_action_date': next_action_date})
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
    if not isinstance(values, dict) or set(values) - {'title','description','accountable_owner','coordination_user','status','next_action','next_action_date','resolution_note','participants','follow_up_assignees'}:
        frappe.throw(_('Invalid fields'))
    for key, val in values.items():
        if key == 'participants': _set_users(doc, 'Participant', val)
        elif key == 'follow_up_assignees': _set_users(doc, 'Follow-up', val)
        elif key == 'coordination_user': doc.coordination_user = _coordination_selection(val, current=getattr(doc, 'coordination_user', None))
        elif key == 'description' and (val or '') != (doc.description or ''): doc.description = _rich_html(val or '', doc)
        elif key != 'description': doc.set(key, val)
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
    _event(doc, 'Communication', before, channel=channel, happened_at=happened_at, body=_rich_html(body, doc), contact=contact)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    return _output(doc)



@frappe.whitelist(methods=['POST'])
def add_comment(name, body, reply_to=None):
    doc = _doc(name, lock=True)
    if reply_to:
        if not isinstance(reply_to, str):
            frappe.throw(_('Invalid reply target'))
        parent = next((event for event in doc.timeline if getattr(event, 'name', None) == reply_to), None)
        # Only roots of this issue can be replied to; nested reply targets are rejected.
        if not parent or parent.kind not in ('Comment', 'Communication') or getattr(parent, 'reply_to', None):
            frappe.throw(_('Invalid reply target'))
    if not isinstance(body, str):
        frappe.throw(_('A comment is required'))
    clean_body = _rich_html(body, doc)
    parsed = BeautifulSoup(clean_body, 'html.parser')
    text = parsed.get_text().replace('\u200b', '').replace('\ufeff', '').strip()
    if not text and not parsed.find('img'):
        frappe.throw(_('A comment is required'))
    # Only mentions actually present in the retained editor content grant access.
    mention_nodes = parsed.select('span[data-type="mention"][data-id]')
    mentioned_users = [node.get('data-id') for node in mention_nodes if node.get_text(strip=True)]
    for user in _users(mentioned_users):
        if not any(row.user == user and row.reason == 'Mention' for row in doc.access):
            doc.append('access', {'user': user, 'reason': 'Mention'})
    _validate(doc)
    _event(doc, 'Comment', body=clean_body, reply_to=reply_to or None)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    return _output(doc)


def _attachment_path(key):
    # These files are outside /private/files and are only exposed through download_attachment.
    if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
        frappe.throw(_('Invalid attachment'))
    return frappe.get_site_path('private', 'unicom', key)


@frappe.whitelist(methods=['POST'])
def upload_attachment(docname, image_only=False):
    doc = _doc(docname, lock=True)
    uploaded = frappe.request.files.get('file')
    if not uploaded: frappe.throw(_('File is required'))
    filename = uploaded.filename
    if not filename or '/' in filename or '\\' in filename: frappe.throw(_('Invalid filename'))
    data = uploaded.stream.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024: frappe.throw(_('Maximum attachment size is 10 MB'))
    if image_only in (True, 1, '1', 'true'): _decoded_image(data)
    key = secrets.token_hex(32)
    path = _attachment_path(key)
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    try:
        with open(path, 'xb') as target:
            target.write(data)
        os.chmod(path, 0o600)
        doc.append('attachments', {'file_name': filename, 'storage_key': key, 'uploaded_by': _user(), 'uploaded_at': now_datetime()})
        doc.flags.unicom_api = True
        doc.save(ignore_permissions=True)
    except Exception:
        if os.path.exists(path): os.unlink(path)
        raise
    return _output(doc)['attachments'][-1]


@frappe.whitelist()
def download_attachment(name, attachment):
    doc = _doc(name)
    row = next((row for row in doc.attachments if row.name == attachment), None)
    if not row: frappe.throw(_('Attachment not found'), frappe.DoesNotExistError)
    with open(_attachment_path(row.storage_key), 'rb') as source:
        frappe.response.filecontent = source.read()
    frappe.response.filename = row.file_name
    frappe.response.type = 'download'


@frappe.whitelist()
def inline_image(name, attachment):
    doc = _doc(name)
    row = next ( (row for row in doc.attachments if row.name == attachment), None)
    if not row: frappe.throw(_('Attachment not found'), frappe.DoesNotExistError)
    with open(_attachment_path(row.storage_key), 'rb') as source:
        data = _decoded_image(source.read())
    return Response(data, content_type='image/png', headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, no-store'})


@frappe.whitelist(methods=['POST'])
def upload_image(docname):
    return upload_attachment(docname, image_only=True)
