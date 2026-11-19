"""The only mutation surface for UniCom records; generic document writes are denied."""
import io
import json
import os
import secrets
import re
from datetime import date, time
from urllib.parse import urlencode
from PIL import Image, UnidentifiedImageError
from werkzeug.wrappers import Response
from bs4 import BeautifulSoup

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today
from unicom.permissions import issue_permission, issue_query
from unicom.notifications import notify_mentions as _notify_mentions

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
    if doc.next_action_date:
        getdate(doc.next_action_date)


def _set_users(doc, reason, users):
    users = _users(users)
    doc.access = [r for r in doc.access if r.reason != reason or r.user in users]
    existing = {r.user for r in doc.access if r.reason == reason}
    for user in users:
        if user not in existing:
            doc.append('access', {'user': user, 'reason': reason})


def _mentioned_users(clean_html):
    # Extract only explicit, nonempty nodes retained by the rich-text sanitizer.
    parsed = BeautifulSoup(clean_html, 'html.parser')
    return list(dict.fromkeys(node.get('data-id') for node in parsed.select('span[data-type="mention"][data-id]') if node.get_text(strip=True)))


def _grant_mentions(doc, clean_html):
    users = _users(_mentioned_users(clean_html))
    for user in users:
        if not any(row.user == user and row.reason == 'Mention' for row in doc.access):
            doc.append('access', {'user': user, 'reason': 'Mention'})
    return users


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
    # A locking fetch is also a current read under MariaDB REPEATABLE READ.
    doc = frappe.get_doc('UniCom Issue', name, for_update=True) if lock else frappe.get_doc('UniCom Issue', name)
    if not issue_permission(doc, user=frappe.session.user, ptype='read'):
        frappe.throw(_('Not permitted'), frappe.PermissionError)
    return doc


def _source_document(doctype, name):
    """Return a currently readable supported source, or None without disclosing details."""
    if not isinstance(doctype, str) or not isinstance(name, str) or not doctype or not name:
        return None
    if doctype.startswith('UniCom ') or any(char in doctype for char in ('`', '\\')) or not frappe.db.exists('DocType', doctype):
        return None
    meta = frappe.get_meta(doctype)
    if meta.istable or meta.issingle or not frappe.db.exists(doctype, name):
        return None
    source = frappe.get_doc(doctype, name)
    return source if frappe.has_permission(doctype, ptype='read', doc=source) else None


def _source_pair(doctype, name):
    if doctype is None and name is None:
        return None, None
    if not _source_document(doctype, name):
        frappe.throw(_('Invalid or inaccessible source document'), frappe.PermissionError)
    return doctype, name


def _lock_source(doctype, name):
    # Quote the validated DocType separately from the bound document name.
    if not doctype or not name or any(char in doctype for char in ('`', '\\')) or not frappe.db.exists('DocType', doctype):
        frappe.throw(_('Source document is no longer available'))
    meta = frappe.get_meta(doctype)
    if meta.istable or meta.issingle or doctype.startswith('UniCom '):
        frappe.throw(_('Source document is no longer available'))
    table = 'tab' + doctype.replace('`', '``')
    if not frappe.db.sql(f'SELECT name FROM `{table}` WHERE name=%s FOR UPDATE', (name,)):
        frappe.throw(_('Source document is no longer available'))


def _active_source_issue(doctype, name, exclude=None, lock=False):
    query = "SELECT name FROM `tabUniCom Issue` WHERE reference_doctype=%s AND reference_name=%s AND status != 'Resolved'"
    args = [doctype, name]
    if exclude:
        query += ' AND name != %s'
        args.append(exclude)
    query += ' ORDER BY name LIMIT 1'
    if lock:
        query += ' FOR UPDATE'
    rows = frappe.db.sql(query, tuple(args))
    return rows[0][0] if rows else None


def _ensure_no_active_source(doctype, name, exclude=None):
    if _active_source_issue(doctype, name, exclude=exclude, lock=True):
        frappe.throw(_('An active issue already exists for this source document'))


@frappe.whitelist()
def source_issue(reference_doctype, reference_name):
    user = _user()
    if not reference_doctype or not reference_name:
        frappe.throw(_('Invalid or inaccessible source document'), frappe.PermissionError)
    _source_pair(reference_doctype, reference_name)
    name = _active_source_issue(reference_doctype, reference_name)
    if not name:
        return {'exists': False}
    issue = frappe.get_doc('UniCom Issue', name)
    if issue_permission(issue, user=user, ptype='read'):
        return {'exists': True, 'name': name}
    return {'exists': True}


def _can_delegate_schedule(doc, user):
    return user == 'Administrator' or user in (doc.owner, doc.accountable_owner)


def _schedule_author_eligible(doc, user):
    return user != 'Guest' and bool(frappe.db.exists('User', {'name': user, 'enabled': 1})) and issue_permission(doc, user=user, ptype='read')


def _output(doc):
    result = doc.as_dict()
    source_doctype = result.pop('reference_doctype', None)
    source_name = result.pop('reference_name', None)
    if _source_document(source_doctype, source_name):
        result.update(reference_doctype=source_doctype, reference_name=source_name)
    result['overdue'] = bool(doc.status != 'Resolved' and doc.next_action_date and getdate(doc.next_action_date) < getdate(today()))
    result['attachments'] = [{'name': row.name, 'file_name': row.file_name, 'file_url': '/api/method/unicom.api.download_attachment?' + urlencode({'name': doc.name, 'attachment': row.name}), 'creation': row.uploaded_at} for row in doc.attachments]
    profile_users = {doc.owner, doc.accountable_owner, getattr(doc, 'coordination_user', None)}
    profile_users.update(event.actor for event in doc.timeline if event.actor)
    profile_users.update(getattr(event, 'scheduled_for', None) for event in doc.timeline)
    profile_users.discard(None)
    profile_users.discard('')
    # This document was already checked for access. Only its referenced people are exposed.
    result['user_profiles'] = frappe.get_all('User', filters={'name': ['in', sorted(profile_users)]}, fields=['name', 'full_name', 'user_image'], limit_page_length=0) if profile_users else []
    candidates = sorted({event.actor for event in doc.timeline if event.kind == 'Comment' and event.actor != 'Guest' and issue_permission(doc, user=event.actor, ptype='read')}) if _can_delegate_schedule(doc, frappe.session.user) else []
    result['schedule_eligible_authors'] = frappe.get_all('User', filters={'name': ['in', candidates], 'enabled': 1}, pluck='name', limit_page_length=0) if candidates else []
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
def list_notifications(start=0, page_length=20):
    from unicom.notifications import list_for_user
    return list_for_user(_user(), start, page_length)


@frappe.whitelist(methods=['POST'])
def mark_notification_read(name):
    from unicom.notifications import mark_read_for_user
    return mark_read_for_user(_user(), name)


@frappe.whitelist()
def get_issue(name):
    return _output(_doc(name))


@frappe.whitelist(methods=['POST'])
def create_issue(title, accountable_owner, next_action='', next_action_date=None, description='', participants=None, follow_up_assignees=None, coordination_user=None, reference_doctype=None, reference_name=None):
    _user()
    reference_doctype, reference_name = _source_pair(reference_doctype, reference_name)
    if reference_doctype:
        _lock_source(reference_doctype, reference_name)
        _ensure_no_active_source(reference_doctype, reference_name)
    doc = frappe.new_doc('UniCom Issue')
    doc.update({'reference_doctype': reference_doctype, 'reference_name': reference_name, 'title': title, 'description': _rich_html(description or ''), 'accountable_owner': accountable_owner, 'coordination_user': _coordination_selection(coordination_user), 'status': 'Open', 'next_action': next_action, 'next_action_date': next_action_date})
    _set_users(doc, 'Participant', participants)
    _set_users(doc, 'Follow-up', follow_up_assignees)
    mentioned_users = _grant_mentions(doc, doc.description)
    _validate(doc)
    _event(doc, 'Created')
    doc.flags.unicom_api = True
    doc.insert(ignore_permissions=True)
    _notify_mentions(doc, mentioned_users, 'description')
    return _output(doc)


@frappe.whitelist(methods=['POST'])
def update_issue(name, values):
    values = _json(values, {})
    if not isinstance(values, dict) or set(values) - {'title','description','accountable_owner','coordination_user','status','next_action','next_action_date','resolution_note','participants','follow_up_assignees'}:
        frappe.throw(_('Invalid fields'))
    # The source pair is immutable. Lock it before the issue for active states.
    source = None
    if values.get('status') in ('Open', 'In Progress', 'Waiting'):
        original = _doc(name)
        if getattr(original, 'reference_doctype', None) and getattr(original, 'reference_name', None):
            source = (original.reference_doctype, original.reference_name)
            _lock_source(*source)
    doc = _doc(name, lock=True)
    if source:
        _ensure_no_active_source(*source, exclude=name)
    before = _snapshot(doc)
    description_mentions = []
    for key, val in values.items():
        if key == 'participants': _set_users(doc, 'Participant', val)
        elif key == 'follow_up_assignees': _set_users(doc, 'Follow-up', val)
        elif key == 'coordination_user': doc.coordination_user = _coordination_selection(val, current=getattr(doc, 'coordination_user', None))
        elif key == 'description' and (val or '') != (doc.description or ''):
            previous_mentions = set(_mentioned_users(doc.description or ''))
            doc.description = _rich_html(val or '', doc)
            description_mentions = [user for user in _grant_mentions(doc, doc.description) if user not in previous_mentions]
        elif key != 'description': doc.set(key, val)
    _validate(doc)
    kind = 'Resolved' if before['status'] != 'Resolved' and doc.status == 'Resolved' else 'Reopened' if before['status'] == 'Resolved' and doc.status != 'Resolved' else 'Updated'
    _event(doc, kind, before)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    _notify_mentions(doc, description_mentions, 'description')
    return _output(doc)


@frappe.whitelist(methods=['POST'])
def log_communication(name, channel, happened_at, body, next_action=None, next_action_date=None, resolution_note=None, contact='', mentions=None, source_comment=None, set_follow_up=None):
    doc = _doc(name, lock=True)
    if doc.status == 'Resolved': frappe.throw(_('Reopen the issue first'))
    if channel not in CHANNELS or not happened_at or not (body or '').strip(): frappe.throw(_('Channel, time and outcome are required'))
    if source_comment:
        source = next((event for event in doc.timeline if event.name == source_comment), None)
        if not source or source.kind != 'Comment' or source.actor != _user():
            frappe.throw(_('Invalid source comment'))
        if any(event.kind == 'Communication' and getattr(event, 'source_comment', None) == source_comment for event in doc.timeline):
            frappe.throw(_('This comment already has a communication log'))
    if set_follow_up is not None and set_follow_up not in (True, False, 0, 1):
        frappe.throw(_('Invalid follow-up selection'))
    if set_follow_up and resolution_note:
        frappe.throw(_('Log a follow-up or resolve the issue, not both'))
    if set_follow_up and not next_action_date:
        frappe.throw(_('A follow-up date is required'))
    if next_action_date:
        getdate(next_action_date)
    before = _snapshot(doc)
    if resolution_note:
        doc.status, doc.resolution_note = 'Resolved', resolution_note
    elif set_follow_up is None:
        doc.next_action, doc.next_action_date = next_action, next_action_date
    elif set_follow_up:
        if next_action and next_action.strip():
            doc.next_action = next_action
        doc.next_action_date = next_action_date
    # Mention grants are durable and separate from participant membership.
    mentioned_users = [node.get('data-id') for node in BeautifulSoup(body, 'html.parser').select('[data-type=mention][data-id]')]
    for user in _users(mentioned_users):
        if not any(r.user == user and r.reason == 'Mention' for r in doc.access): doc.append('access', {'user': user, 'reason': 'Mention'})
    _validate(doc)
    _event(doc, 'Communication', before, channel=channel, happened_at=happened_at, body=_rich_html(body, doc), contact=contact, source_comment=source_comment or None, follow_up_action=next_action, follow_up_date=next_action_date)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    return _output(doc)


@frappe.whitelist(methods=['POST'])
def schedule_event(name, schedule_type, scheduled_date, title, contact='', scheduled_time=None, source_comment=None, set_follow_up=False):
    doc = _doc(name, lock=True)
    if doc.status not in ('Open', 'In Progress', 'Waiting'):
        frappe.throw(_('Reopen the issue first'))
    if schedule_type not in ('Meeting', 'Follow-up'):
        frappe.throw(_('Select a meeting or follow-up'))
    if not isinstance(title, str) or not title.strip() or len(title) > 140:
        frappe.throw(_('A title of up to 140 characters is required'))
    if not isinstance(contact, str) or len(contact) > 140:
        frappe.throw(_('Invalid contact'))
    if not isinstance(scheduled_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', scheduled_date):
        frappe.throw(_('A valid scheduled date is required'))
    try:
        date.fromisoformat(scheduled_date)
    except ValueError:
        frappe.throw(_('A valid scheduled date is required'))
    if scheduled_time not in (None, ''):
        if not isinstance(scheduled_time, str) or not re.fullmatch(r'\d{2}:\d{2}(?::\d{2})?', scheduled_time):
            frappe.throw(_('Invalid scheduled time'))
        try:
            scheduled_time = time.fromisoformat(scheduled_time).isoformat()
        except ValueError:
            frappe.throw(_('Invalid scheduled time'))
    if type(set_follow_up) not in (bool, int) or set_follow_up not in (0, 1):
        frappe.throw(_('Invalid follow-up selection'))
    scheduled_for = _user()
    if source_comment:
        source = next((event for event in doc.timeline if event.name == source_comment), None)
        if not source or source.kind != 'Comment' or (source.actor != _user() and not _can_delegate_schedule(doc, _user())):
            frappe.throw(_('Invalid source comment'))
        scheduled_for = source.actor
        if any(event.kind == 'Scheduled' and getattr(event, 'source_comment', None) == source_comment for event in doc.timeline):
            frappe.throw(_('This comment already has a scheduled event'))
    if not _schedule_author_eligible(doc, scheduled_for):
        frappe.throw(_('The comment author cannot currently access this issue'), frappe.PermissionError)
    before = _snapshot(doc)
    if set_follow_up:
        doc.next_action, doc.next_action_date = title.strip(), scheduled_date
    _validate(doc)
    _event(doc, 'Scheduled', before, schedule_type=schedule_type, follow_up_date=scheduled_date,
           follow_up_action=title.strip(), contact=contact.strip(), scheduled_time=scheduled_time or None,
           source_comment=source_comment or None, scheduled_for=scheduled_for)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    return _output(doc)


@frappe.whitelist(methods=['POST'])
def complete_scheduled_event(name, event_name):
    doc = _doc(name, lock=True)
    event = next((row for row in doc.timeline if row.name == event_name), None)
    if not event or event.kind != 'Scheduled' or (getattr(event, 'scheduled_for', None) or event.actor) != _user():
        frappe.throw(_('Not permitted'), frappe.PermissionError)
    if getattr(event, 'completed_at', None):
        return _output(doc)
    if doc.status not in ('Open', 'In Progress', 'Waiting'):
        frappe.throw(_('Reopen the issue first'))
    event.completed_at = now_datetime()
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    return _output(doc)


@frappe.whitelist(methods=['GET'])
def today_schedule():
    user, day = _user(), today()
    permission = issue_query(user)
    rows = frappe.db.sql("""SELECT e.name, e.parent AS issue_name,
        `tabUniCom Issue`.issue_id, `tabUniCom Issue`.title AS issue_title,
        e.follow_up_action AS title, e.contact, e.follow_up_date AS scheduled_date,
        e.scheduled_time, e.schedule_type
        FROM `tabUniCom Issue Event` e
        INNER JOIN `tabUniCom Issue` ON `tabUniCom Issue`.name = e.parent
        WHERE e.parenttype = 'UniCom Issue' AND e.parentfield = 'timeline'
        AND e.kind = 'Scheduled' AND COALESCE(NULLIF(e.scheduled_for, ''), e.actor) = %s AND e.follow_up_date = %s
        AND e.completed_at IS NULL AND `tabUniCom Issue`.status IN ('Open','In Progress','Waiting')
        """ + (' AND (' + permission + ')' if permission else '') + """
        ORDER BY e.scheduled_time IS NULL, e.scheduled_time, e.recorded_at, e.name""", (user, day), as_dict=True)
    for row in rows:
        row['scheduled_date'] = str(row['scheduled_date'])
        if row.get('scheduled_time') is not None:
            row['scheduled_time'] = str(row['scheduled_time']).zfill(8)
    return {'date': day, 'items': rows}



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
    mentioned_users = _grant_mentions(doc, clean_body)
    _validate(doc)
    _event(doc, 'Comment', body=clean_body, reply_to=reply_to or None)
    doc.flags.unicom_api = True
    doc.save(ignore_permissions=True)
    _notify_mentions(doc, mentioned_users, 'reply' if reply_to else 'comment')
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
