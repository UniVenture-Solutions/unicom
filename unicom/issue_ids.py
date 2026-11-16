"""Atomic public issue identifiers. Internal document names remain unchanged."""
import frappe
from frappe.model.naming import make_autoname

SERIES_KEY = 'ISU-'
SERIES_PATTERN = 'ISU-.####'


def lock_series():
    # Seed safely even when two transactions create the first issue simultaneously.
    frappe.db.sql("INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, 0) ON DUPLICATE KEY UPDATE `name` = `name`", SERIES_KEY)
    frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name` = %s FOR UPDATE", SERIES_KEY)


def next_issue_id():
    lock_series()
    return make_autoname(SERIES_PATTERN)
