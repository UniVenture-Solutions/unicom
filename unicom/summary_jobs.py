"""Best-effort, revision-scoped background summaries; never publish issue changes."""
import hashlib
import json
import frappe
from frappe.utils import get_datetime


def revision(value):
    return get_datetime(value).isoformat(sep=' ', timespec='microseconds')


def fresh(doc):
    try:
        data = json.loads(doc.ai_summary or '')
        return bool(data.get('version') == 1 and data.get('generated_at') and data.get('issue') and data.get('current_status') and isinstance(data.get('steps_to_resolve'), list) and data.get('source_revision') == revision(doc.modified))
    except (ValueError, TypeError, AttributeError):
        return False


def available():
    try:
        return 'uniai' in frappe.get_installed_apps() and bool(frappe.db.get_single_value('UniAI Settings', 'enabled'))
    except Exception:
        return False


def job_id(name, source_revision):
    return 'unicom-summary-' + hashlib.sha256((name + ':' + source_revision).encode()).hexdigest()


def pending(name, source_revision):
    try:
        from frappe.utils.background_jobs import is_job_enqueued
        return bool(is_job_enqueued(job_id(name, source_revision)))
    except Exception:
        return False


def queue_summary(name, modified, requested_by):
    if not available():
        return False
    try:
        source_revision = revision(modified)
    except Exception:
        return False
    def enqueue():
        try:
            frappe.enqueue('unicom.summary_jobs.generate', queue='long', timeout=90,
                job_id=job_id(name, source_revision), deduplicate=True,
                name=name, source_revision=source_revision, requested_by=requested_by)
        except Exception:
            frappe.logger('unicom').warning('Automatic summary could not be queued')
    try:
        frappe.db.after_commit.add(enqueue)
        return True
    except Exception:
        return False


def generate(name, source_revision, requested_by):
    try:
        if frappe.session.user != requested_by or not available():
            return
        from unicom.api import _doc, _generate_issue_summary
        from unicom.permissions import issue_action_permission
        doc = _doc(name)
        if not issue_action_permission(doc, user=requested_by) or revision(doc.modified) != source_revision or fresh(doc):
            return
        _generate_issue_summary(name, expected_revision=source_revision)
    except Exception:
        frappe.db.rollback()
        frappe.logger('unicom').warning('Automatic summary generation was unavailable')
