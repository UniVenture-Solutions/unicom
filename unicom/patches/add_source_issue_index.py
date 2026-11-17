"""Narrow active-source locking reads to the relevant reference range."""
import frappe


def execute():
    frappe.db.add_index('UniCom Issue', ['reference_doctype', 'reference_name', 'status'], 'unicom_source_status_idx')
