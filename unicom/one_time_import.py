"""Temporary Administrator-only HTTP surface for the approved transfer."""
import hashlib
import hmac
import secrets

import frappe
from unicom import selected_transfer as transfer

ORIGIN = 'https://' + transfer.TARGET_HOST


def _host_allowed():
    request = getattr(frappe.local, 'request', None)
    return bool(request and request.host.lower() in (transfer.TARGET_HOST, transfer.TARGET_HOST + ':443') and frappe.local.site != transfer.SOURCE_SITE)


def _require_admin_post():
    request = getattr(frappe.local, 'request', None)
    if not _host_allowed() or frappe.session.user != 'Administrator' or request.method != 'POST':
        frappe.throw('Administrator access is required on the destination site.', frappe.PermissionError)
    saved = frappe.session.data.get('csrf_token')
    supplied = request.headers.get('X-Frappe-CSRF-Token', '')
    if request.headers.get('Origin') != ORIGIN or not isinstance(saved, str) or not saved or not isinstance(supplied, str) or not hmac.compare_digest(saved, supplied):
        frappe.throw('Reload this Administrator page before continuing.', frappe.CSRFTokenError)
    frappe.local.response.setdefault('headers', {})['Cache-Control'] = 'no-store, private'


def _key(token):
    if not isinstance(token, str) or len(token) > 80 or len(token) < 32:
        raise ValueError('Preview expired; preview again')
    session = hashlib.sha256((frappe.local.site + ':' + frappe.session.sid).encode()).hexdigest()
    return 'unicom-approved-transfer:' + session + ':' + token


def _metadata(report, source):
    plan = report['plan']
    names = {user['name']: user['full_name'] for user in source['referenced_users']}
    return {'plan_sha256': report['plan_sha256'], 'snapshot_captured_at': source.get('captured_at', ''), 'snapshot_timezone': source.get('source_timezone', ''), 'needs_apply': any(item['action'] == 'create' for item in plan['issues']) or plan['series_after'] > plan['series_before'], 'issue_count': len(plan['issues']),
            'event_count': sum(item['event_count'] for item in plan['issues']),
            'comment_count': 58, 'issues': [{'issue_id': item['source_issue_id'], 'action': item['action']} for item in plan['issues']],
            'user_mappings': [{'source_name': names[row['source_user']], 'target_name': row['target_full_name'], 'target_user': row['target_user']} for row in plan['identities']]}


def _blocked(error):
    message = str(error)
    # Only reviewed preflight messages may reach the UI; never SQL/tracebacks/data.
    prefixes = ('Destination account needs review:', 'Existing, changed or conflicting destination issue:',
                'Existing/conflicting timeline ID:', 'Orphaned destination child rows:',
                'Partial existing batch;', 'Incompatible schema:', 'Incompatible user/table links:',
                'Incompatible parent/child schema:', 'Missing columns or unsupported mandatory fields:',
                'Destination cannot preserve microsecond metadata:', 'Preview plan changed;',
                'Preview expired;', 'Preview is no longer valid;', 'Source snapshot hash differs',
                'Invalid approved snapshot', 'Requires installed UniCom on Frappe v16',
                'Timezone differs;', 'UniCom record permissions are not installed',
                'Transfer requires transactional InnoDB tables', 'Malformed destination issue ID',
                'Expected four distinct verified user identities')
    return {'ok': False, 'message': message if isinstance(error, ValueError) and message.startswith(prefixes) else 'The transfer could not be confirmed. Preview again to check the current state.'}


@frappe.whitelist(methods=['POST'])
def preview(snapshot):
    _require_admin_post()
    try:
        source = transfer.load_source(snapshot)
        report = transfer.run(snapshot, frappe.local.site)
        token = secrets.token_urlsafe(32)
        key = _key(token)
        value = {'plan_sha256': report['plan_sha256'], 'snapshot_sha256': transfer.SOURCE_SHA}
        frappe.cache.set_value(key, value, expires_in_sec=900)
        if frappe.cache.get_value(key, expires=True, use_local_cache=False) != value:
            raise ValueError('Preview is no longer valid; preview again')
        return {'ok': True, 'preview_token': token, **_metadata(report, source)}
    except Exception as error:
        return _blocked(error)


@frappe.whitelist(methods=['POST'])
def apply(snapshot, preview_token, plan_sha256):
    _require_admin_post()
    try:
        source = transfer.load_source(snapshot)
        key = _key(preview_token)
        saved = frappe.cache.get_value(key, expires=True, use_local_cache=False)
        if not saved or saved != {'plan_sha256': plan_sha256, 'snapshot_sha256': transfer.SOURCE_SHA}:
            raise ValueError('Preview expired; preview again')
        report = transfer.run(snapshot, frappe.local.site, apply=True, expected_plan_sha=plan_sha256)
        frappe.cache.delete_value(key)
        return {'ok': True, 'completed': True, **_metadata(report, source)}
    except Exception as error:
        frappe.db.rollback()
        return _blocked(error)
