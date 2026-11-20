"""Private, after-commit GoWA notices for newly saved UniCom comments only."""
import hashlib
import re
from urllib.parse import quote, urlsplit, urlunsplit

import frappe
from frappe.utils import cint
from unicom.access import has_management_access


def _warn(message):
    try:
        frappe.logger('unicom').warning(message)
    except Exception:
        pass


def _enabled():
    return 'gowa_chatbot' in frappe.get_installed_apps() and cint(frappe.db.get_single_value('GoWA Chatbot Settings', 'enabled')) == 1


def _international_jid(mobile):
    # Accept explicit +international or the specifically confirmed Pakistan 923 format.
    # National 03 numbers remain ambiguous and must never gain a guessed country.
    if not isinstance(mobile, str):
        return None
    mobile = mobile.strip()
    if re.fullmatch(r'923[0-9]{9}', mobile):
        return mobile + '@s.whatsapp.net'
    if re.fullmatch(r'\+[1-9][0-9]{7,14}', mobile):
        return mobile[1:] + '@s.whatsapp.net'
    return None


def _issue_link(name):
    # Queue workers must not derive private links from a caller-controlled Host.
    origin = frappe.conf.get('host_name') or ('https://' + frappe.local.site)
    if '://' not in origin:
        origin = 'https://' + origin
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, '/unicom/' + quote(name, safe=''), '', ''))


def _enqueue_safely(issue_name, comment_name):
    try:
        if not _enabled():
            return
        digest = hashlib.sha256((issue_name + ':' + comment_name).encode()).hexdigest()
        frappe.enqueue('unicom.owner_notifications.notify_owner_of_comment', queue='short', timeout=60,
                       issue_name=issue_name, comment_name=comment_name,
                       job_id='unicom_owner_comment_' + digest, deduplicate=True)
    except Exception:
        _warn('UniCom owner WhatsApp notice could not be queued.')


def queue_owner_comment(issue_name, comment_name):
    try:
        if any(not isinstance(value, str) or not value or len(value) > 140 for value in (issue_name, comment_name)):
            return
        # Guard the callback too: a Redis failure AFTER commit must not fail the UI.
        frappe.db.after_commit.add(lambda: _enqueue_safely(issue_name, comment_name))
    except Exception:
        _warn('UniCom owner WhatsApp notice could not be registered.')


def notify_owner_of_comment(issue_name, comment_name):
    try:
        if any(not isinstance(value, str) or not value or len(value) > 140 for value in (issue_name, comment_name)) or not _enabled():
            return False
        comment = frappe.db.get_value('UniCom Issue Event', {'name': comment_name, 'parent': issue_name,
                     'parenttype': 'UniCom Issue', 'parentfield': 'timeline', 'kind': 'Comment'}, ['name', 'reply_to'], as_dict=True)
        issue = frappe.db.get_value('UniCom Issue', issue_name, ['accountable_owner', 'issue_id'], as_dict=True)
        if not comment or not issue or not has_management_access(issue.accountable_owner):
            return False
        owner = frappe.db.get_value('User', issue.accountable_owner, ['enabled', 'mobile_no'], as_dict=True)
        if not owner or not cint(owner.enabled):
            return False
        jid, link = _international_jid(owner.mobile_no), _issue_link(issue_name)
        if not jid or not link:
            return False
        settings = frappe.get_single('GoWA Chatbot Settings')
        if not cint(settings.enabled):
            return False
        from gowa_chatbot.client import Client
        kind = 'reply' if comment.reply_to else 'comment'
        message = 'New ' + kind + ' on ' + (issue.issue_id or issue_name) + '\n' + link
        Client(settings).request('POST', '/send/message', json={'phone': jid, 'message': message})
        return True
    except Exception:
        # Never log phone numbers, gateway credentials/responses, or comment text.
        _warn('UniCom owner WhatsApp notice could not be delivered.')
        return False
