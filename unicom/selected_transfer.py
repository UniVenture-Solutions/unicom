"""Strict core for the approved one-time UniCom transfer; no public methods.

Only the hash-pinned in-memory JSON is accepted. Preview is read-only. Apply
uses raw transactional inserts to retain history without workflow notifications.
"""
import copy
import hashlib
import json
from pathlib import Path
import re
import stat
from urllib.parse import urlparse

SOURCE_SHA = 'b85d7093a38feb93d1243b6ffe65442766beee68e58b96ae6ba344101ce765e8'
SOURCE_SITE = 'unitrade.dev.univenturescloud.com'
TARGET_HOST = 'univenturetraders.com'
IDS = ('ISU-0014', 'ISU-0015', 'ISU-0016', 'ISU-0017', 'ISU-0018')
STANDARD = ('name', 'owner', 'creation', 'modified', 'modified_by', 'docstatus', 'idx')
PARENT = STANDARD + ('issue_id', 'title', 'description', 'accountable_owner', 'coordination_user', 'reference_doctype', 'reference_name', 'status', 'next_action', 'next_action_date', 'resolution_note')
EVENT = STANDARD + ('parent', 'parenttype', 'parentfield', 'kind', 'actor', 'recorded_at', 'happened_at', 'channel', 'contact', 'body', 'changes', 'reply_to')
SCHEMA = {
    'UniCom Issue': {'issue_id': 'Data', 'title': 'Data', 'description': 'Text Editor', 'accountable_owner': 'Link', 'coordination_user': 'Link', 'reference_doctype': 'Data', 'reference_name': 'Data', 'status': 'Select', 'next_action': 'Small Text', 'next_action_date': 'Date', 'resolution_note': 'Small Text', 'access': 'Table', 'timeline': 'Table', 'attachments': 'Table'},
    'UniCom Issue Event': {'kind': 'Select', 'actor': 'Link', 'recorded_at': 'Datetime', 'happened_at': 'Datetime', 'channel': 'Select', 'contact': 'Data', 'body': 'Text Editor', 'changes': 'Long Text', 'reply_to': 'Data'},
    'UniCom Issue Access': {'user': 'Link', 'reason': 'Select'},
    'UniCom Issue Attachment': {'file_name': 'Data', 'storage_key': 'Data', 'uploaded_by': 'Link', 'uploaded_at': 'Datetime'},
}
OPTIONS = {'UniCom Issue': {'accountable_owner': 'User', 'coordination_user': 'User', 'access': 'UniCom Issue Access', 'timeline': 'UniCom Issue Event', 'attachments': 'UniCom Issue Attachment'}, 'UniCom Issue Event': {'actor': 'User'}, 'UniCom Issue Access': {'user': 'User'}, 'UniCom Issue Attachment': {'uploaded_by': 'User'}}
CHILDREN = {'timeline': 'UniCom Issue Event', 'access': 'UniCom Issue Access', 'attachments': 'UniCom Issue Attachment'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, default=str)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def load_source(raw):
    if isinstance(raw, str): raw = raw.encode('utf-8')
    if not isinstance(raw, bytes) or len(raw) > 100 * 1024: raise ValueError('Invalid approved snapshot')
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('Source snapshot hash differs')
    source = json.loads(raw)
    if source['format'] != 'unicom-selected-issue-transfer-v1' or source['source_site'] != SOURCE_SITE or source['source_timezone'] != 'Asia/Karachi' or tuple(source['selected_issue_ids']) != IDS:
        raise ValueError('Unexpected source scope')
    issues = source['issues']
    if len(issues) != 5 or tuple(row['issue_id'] for row in issues) != IDS or source['attachment_blob_manifest'] or source['missing_referenced_user_ids']:
        raise ValueError('Unexpected source records, files or missing users')
    names = set()
    count = 0
    for doc in issues:
        if set(doc) != set(PARENT) | {'doctype', *CHILDREN} or doc['doctype'] != 'UniCom Issue' or doc['status'] != 'Open' or doc['docstatus'] != 0:
            raise ValueError('Incompatible source parent fields/state')
        if doc['access'] or doc['attachments'] or doc['reference_doctype'] or doc['reference_name']:
            raise ValueError('This reviewed transfer has no access rows, attachments or ERP references')
        if digest(doc) != source['record_manifest'][doc['issue_id']]['sha256']:
            raise ValueError('Source record manifest differs')
        for index, row in enumerate(doc['timeline'], 1):
            if set(row) != set(EVENT) | {'doctype'} or row['doctype'] != 'UniCom Issue Event' or row['parent'] != doc['name'] or row['parenttype'] != 'UniCom Issue' or row['parentfield'] != 'timeline' or row['idx'] != index or row['reply_to']:
                raise ValueError('Incompatible source timeline relationships')
            if row['name'] in names:
                raise ValueError('Duplicate source event ID')
            names.add(row['name']); count += 1
    if count != 67 or sum(row['kind'] == 'Comment' for doc in issues for row in doc['timeline']) != 58:
        raise ValueError('Expected 67 events including 58 comments')
    return source


def target_preflight(expected_site):
    import frappe
    if frappe.session.user != 'Administrator' or not expected_site or frappe.local.site != expected_site or expected_site == SOURCE_SITE:
        raise ValueError('Requires Administrator on the explicitly verified destination site')
    hosts = {str(frappe.local.site).lower()}
    request = getattr(frappe.local, 'request', None)
    if request and request.host.lower() in (TARGET_HOST, TARGET_HOST + ':443'):
        hosts.add(TARGET_HOST)
    configured = frappe.conf.get('host_name')
    if configured:
        hosts.add(urlparse(configured if '://' in configured else 'https://' + configured).hostname)
    domains = frappe.conf.get('domains') or []
    for domain in ([domains] if isinstance(domains, str) else domains):
        value = domain.get('domain') if isinstance(domain, dict) else domain
        if isinstance(value, str): hosts.add(value.lower())
    if TARGET_HOST not in hosts:
        raise ValueError('Destination site is not configured for univenturetraders.com')
    if str(frappe.__version__).split('.')[0] != '16' or 'unicom' not in frappe.get_installed_apps():
        raise ValueError('Requires installed UniCom on Frappe v16')
    if frappe.db.get_single_value('System Settings', 'time_zone') != 'Asia/Karachi':
        raise ValueError('Timezone differs; timestamp conversion is not authorized')
    for hook, method in (('has_permission', 'unicom.permissions.issue_permission'), ('permission_query_conditions', 'unicom.permissions.issue_query')):
        configured = frappe.get_hooks(hook).get('UniCom Issue', [])
        if method not in ([configured] if isinstance(configured, str) else configured):
            raise ValueError('UniCom record permissions are not installed')
    tables = ['tab' + name for name in SCHEMA] + ['tabSeries', 'tabUser']
    engines = frappe.db.sql('SELECT TABLE_NAME AS table_name, ENGINE AS engine FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN (' + ','.join(['%s'] * len(tables)) + ')', tuple(tables), as_dict=True)
    if {row.table_name for row in engines} != set(tables) or any(str(row.engine).upper() != 'INNODB' for row in engines):
        raise ValueError('Transfer requires transactional InnoDB tables')
    for doctype, expected in SCHEMA.items():
        meta = frappe.get_meta(doctype)
        if bool(meta.istable) != (doctype != 'UniCom Issue') or meta.issingle: raise ValueError('Incompatible parent/child schema: ' + doctype)
        fields = {field.fieldname: field for field in meta.fields}
        if any(name not in fields or fields[name].fieldtype != kind for name, kind in expected.items()):
            raise ValueError('Incompatible schema: ' + doctype)
        if any(fields[name].options != option for name, option in OPTIONS[doctype].items()):
            raise ValueError('Incompatible user/table links: ' + doctype)
        columns = set(frappe.db.get_table_columns(doctype))
        required = set(STANDARD) | {name for name, kind in expected.items() if kind != 'Table'}
        if doctype != 'UniCom Issue': required.update(('parent', 'parenttype', 'parentfield'))
        if not required <= columns or any(getattr(field, 'reqd', 0) and field.fieldname not in expected and (field.fieldname in columns or field.fieldtype in ('Table', 'Table MultiSelect')) for field in meta.fields):
            raise ValueError('Missing columns or unsupported mandatory fields: ' + doctype)
        datetimes = {'creation', 'modified'} | {name for name, kind in expected.items() if kind == 'Datetime'}
        precision = frappe.db.sql('SELECT COLUMN_NAME AS fieldname, DATETIME_PRECISION AS precision_value FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s AND DATA_TYPE=%s', ('tab' + doctype, 'datetime'), as_dict=True)
        if any(next((row.precision_value for row in precision if row.fieldname == name), None) != 6 for name in datetimes):
            raise ValueError('Destination cannot preserve microsecond metadata: ' + doctype)


def user_mapping(source, lock=False):
    import frappe
    mapping = {}
    identities = []
    for source_user in sorted(source['referenced_users'], key=lambda row: row['email'].lower()):
        email = source_user['email'].strip().lower()
        rows = frappe.db.sql('SELECT name,email,full_name,enabled,user_type FROM `tabUser` WHERE email=%s ORDER BY name' + (' FOR UPDATE' if lock else ''), (email,), as_dict=True)
        # A source Administrator can denote a real person who also has a named
        # destination login. Resolve only this exact, fully verified two-row pair.
        if (source_user['name'] == 'Administrator' and len(rows) == 2
                and {row.name for row in rows} == {'Administrator', email}
                and all(row.email.strip().lower() == email and row.enabled and row.user_type == 'System User' for row in rows)):
            rows = [row for row in rows if row.name == email]
        if len(rows) != 1 or rows[0].email.strip().lower() != email or not rows[0].enabled or rows[0].user_type != 'System User':
            raise ValueError('Destination account needs review: ' + source_user['full_name'])
        target = rows[0]
        mapping[source_user['name']] = target.name
        identities.append({'source_user': source_user['name'], 'email': email, 'target_user': target.name, 'target_full_name': target.full_name, 'target_type': target.user_type})
    if len(mapping) != 4 or len(set(mapping.values())) != 4:
        raise ValueError('Expected four distinct verified user identities')
    return mapping, identities


def mapped_issues(source, mapping):
    docs = copy.deepcopy(source['issues'])
    def mapped(user):
        if user not in mapping:
            raise ValueError('Unverified user reference: ' + str(user))
        return mapping[user]
    for doc in docs:
        for key in ('owner', 'modified_by', 'accountable_owner', 'coordination_user'):
            if doc.get(key): doc[key] = mapped(doc[key])
        for row in doc['timeline']:
            for key in ('owner', 'modified_by', 'actor'):
                row[key] = mapped(row[key])
            changes = json.loads(row['changes'] or '{}')
            updated = copy.deepcopy(changes)
            for field in ('accountable_owner', 'coordination_user', 'participants', 'follow_up_assignees'):
                for side, value in changes.get(field, {}).items():
                    if side not in ('from', 'to'): raise ValueError('Unexpected history structure')
                    updated[field][side] = [mapped(user) for user in value] if isinstance(value, list) else mapped(value) if value else value
            if updated != changes: row['changes'] = canonical(updated)
    return docs


def fetch_doc(name, lock=False):
    import frappe
    suffix = ' FOR UPDATE' if lock else ''
    rows = frappe.db.sql('SELECT ' + ','.join('`' + name + '`' for name in PARENT) + ' FROM `tabUniCom Issue` WHERE name=%s' + suffix, (name,), as_dict=True)
    if not rows: return None
    doc = dict(rows[0]); doc['doctype'] = 'UniCom Issue'
    for field, doctype in CHILDREN.items():
        fields = EVENT if field == 'timeline' else STANDARD + ('parent', 'parenttype', 'parentfield') + tuple(SCHEMA[doctype])
        children = frappe.db.sql('SELECT ' + ','.join('`' + name + '`' for name in fields) + ' FROM `tab' + doctype + '` WHERE parent=%s AND parenttype=%s AND parentfield=%s ORDER BY idx' + suffix, (doc['name'], 'UniCom Issue', field), as_dict=True)
        doc[field] = [{**dict(child), 'doctype': doctype} for child in children]
    return doc


def collision_plan(docs, lock=False):
    import frappe
    plans = []
    suffix = ' FOR UPDATE' if lock else ''
    for doc in docs:
        source_link = re.search(r'https://platform\.univenturesgroup\.com/[^"<>\s]+/tracker/UNIVE-\d+', doc['description'])
        if not source_link: raise ValueError('Missing original source provenance')
        matches = frappe.db.sql('SELECT name,issue_id FROM `tabUniCom Issue` WHERE name=%s OR issue_id=%s OR title=%s OR description LIKE %s' + suffix, (doc['name'], doc['issue_id'], doc['title'], '%' + source_link.group() + '%'), as_dict=True)
        if matches:
            if len(matches) != 1 or matches[0].name != doc['name'] or matches[0].issue_id != doc['issue_id'] or digest(fetch_doc(doc['name'], lock)) != digest(doc):
                raise ValueError('Existing, changed or conflicting destination issue: ' + doc['issue_id'])
            action = 'skip_complete'
        else:
            for field, doctype in CHILDREN.items():
                if frappe.db.sql('SELECT name FROM `tab' + doctype + '` WHERE parent=%s AND parenttype=%s AND parentfield=%s' + suffix, (doc['name'], 'UniCom Issue', field)):
                    raise ValueError('Orphaned destination child rows: ' + doc['issue_id'])
            for event in doc['timeline']:
                if frappe.db.sql('SELECT name FROM `tabUniCom Issue Event` WHERE name=%s' + suffix, (event['name'],)):
                    raise ValueError('Existing/conflicting timeline ID: ' + event['name'])
            action = 'create'
        plans.append({'source_issue_id': doc['issue_id'], 'target_name': doc['name'], 'action': action, 'mapped_sha256': digest(doc), 'event_count': len(doc['timeline'])})
    if len({item['action'] for item in plans}) != 1:
        raise ValueError('Partial existing batch; manual reconciliation required')
    return plans


def run(snapshot, expected_site, apply=False, expected_plan_sha=None):
    import frappe
    source = load_source(snapshot)
    target_preflight(expected_site)
    try:
        series_before = frappe.db.sql('SELECT current FROM `tabSeries` WHERE name=%s', ('ISU-',))
        if apply:
            from unicom.issue_ids import lock_series
            lock_series()
        mapping, identities = user_mapping(source, lock=apply)
        docs = mapped_issues(source, mapping)
        plans = collision_plan(docs, lock=apply)
        series = frappe.db.sql('SELECT current FROM `tabSeries` WHERE name=%s' + (' FOR UPDATE' if apply else ''), ('ISU-',))
        current = int(series[0][0]) if series else 0
        existing = frappe.db.sql('SELECT issue_id FROM `tabUniCom Issue`' + (' FOR UPDATE' if apply else ''))
        numbers = []
        for row in existing:
            match = re.fullmatch(r'ISU-([0-9]{4,})', row[0] or '')
            if not match or int(match[1]) < 1 or row[0] != f'ISU-{int(match[1]):04d}': raise ValueError('Malformed destination issue ID')
            numbers.append(int(match[1]))
        high = max([current, 18, *numbers])
        plan = {'source_snapshot_sha256': SOURCE_SHA, 'source_data_sha256': digest({'issues': source['issues'], 'referenced_users': source['referenced_users']}), 'target_site': expected_site, 'target_host': TARGET_HOST, 'timezone': 'Asia/Karachi', 'identities': identities, 'issues': plans, 'series_before': current, 'series_after': high}
        plan_sha = digest(plan)
        report = {'plan': plan, 'plan_sha256': plan_sha, 'applied': bool(apply)}
        if not apply: return report
        if plan_sha != expected_plan_sha:
            raise ValueError('Preview plan changed; preview again before importing')
        directory = Path(frappe.get_site_path('private', 'backups', 'unicom-transfer-' + SOURCE_SHA[:12]))
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode) != 0o700: raise ValueError('Migration archive directory is not private')
        archive = canonical({'state': 'prepared-before-commit', 'report': report, 'target_before': {doc['name']: None if item['action'] == 'create' else doc for doc, item in zip(docs, plans)}, 'series_before': {'existed_before_lock': bool(series_before), 'locked_current': current}, 'mapped_records': docs}).encode()
        path = directory / ('prepared-' + plan_sha + '.json')
        if path.exists():
            if path.is_symlink() or path.read_bytes() != archive or stat.S_IMODE(path.stat().st_mode) != 0o600: raise ValueError('Migration archive differs')
        else:
            with path.open('xb') as output:
                path.chmod(0o600); output.write(archive); output.flush()
                import os
                os.fsync(output.fileno())
        if path.read_bytes() != archive: raise ValueError('Migration archive verification failed')
        import os
        descriptor = os.open(directory, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        for doc, item in zip(docs, plans):
            if item['action'] != 'create': continue
            rows = [('UniCom Issue', PARENT, doc)] + [('UniCom Issue Event', EVENT, event) for event in doc['timeline']]
            for doctype, fields, row in rows:
                frappe.db.sql('INSERT INTO `tab' + doctype + '` (' + ','.join('`' + field + '`' for field in fields) + ') VALUES (' + ','.join(['%s'] * len(fields)) + ')', tuple(row.get(field) for field in fields))
        frappe.db.sql('UPDATE `tabSeries` SET current=GREATEST(COALESCE(current,0),%s) WHERE name=%s', (high, 'ISU-'))
        saved_series = frappe.db.sql('SELECT current FROM `tabSeries` WHERE name=%s FOR UPDATE', ('ISU-',))
        if len(saved_series) != 1 or int(saved_series[0][0]) < high: raise ValueError('Issue series did not advance safely')
        if any(digest(fetch_doc(doc['name'], lock=True)) != digest(doc) for doc in docs):
            raise ValueError('Post-transfer record verification failed')
        frappe.db.commit()
        report['prepared_archive'] = str(path)
        return report
    except Exception:
        if apply: frappe.db.rollback()
        raise
