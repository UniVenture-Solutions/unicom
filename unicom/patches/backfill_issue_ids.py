"""Assign public IDs without changing any document names or modified timestamps."""
import re
import frappe
from unicom.issue_ids import SERIES_KEY, lock_series, next_issue_id


def execute():
    # Migration runs in maintenance mode. Keep lock order consistent with inserts.
    lock_series()
    rows = frappe.db.sql("SELECT name, issue_id FROM `tabUniCom Issue` ORDER BY creation, name FOR UPDATE", as_dict=True)
    seen = set()
    high = 0
    for row in rows:
        if not row.issue_id:
            continue
        if not re.fullmatch(r'ISU-[0-9]{4,}', row.issue_id):
            frappe.throw('Conflicting or invalid UniCom issue IDs; backfill stopped')
        number = int(row.issue_id[4:])
        if number < 1 or row.issue_id != f'ISU-{number:04d}' or row.issue_id in seen:
            frappe.throw('Conflicting or invalid UniCom issue IDs; backfill stopped')
        seen.add(row.issue_id)
        high = max(high, number)
    frappe.db.sql("UPDATE `tabSeries` SET `current` = GREATEST(COALESCE(`current`, 0), %s) WHERE `name` = %s", (high, SERIES_KEY))
    for row in rows:
        if not row.issue_id:
            frappe.db.set_value('UniCom Issue', row.name, 'issue_id', next_issue_id(), update_modified=False)
