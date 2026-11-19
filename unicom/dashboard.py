"""Read-only, current-user receivable aggregates using Frappe's query permissions."""
from decimal import Decimal
import frappe
from frappe.model import get_permitted_fields
from frappe.utils import add_days, today

INVOICE_FIELDS = {'name', 'docstatus', 'is_return', 'posting_date', 'outstanding_amount', 'party_account_currency'}


def receivables_summary(user):
    unavailable = {'available': False}
    if 'erpnext' not in frappe.get_installed_apps() or not frappe.db.exists('DocType', 'Sales Invoice'):
        return unavailable
    if not frappe.has_permission('Sales Invoice', ptype='read', user=user):
        return unavailable
    if not INVOICE_FIELDS.issubset(get_permitted_fields('Sales Invoice', user=user, permission_type='read')):
        return unavailable
    amount_field = frappe.get_meta('Sales Invoice').get_field('outstanding_amount')
    if not amount_field or amount_field.fieldtype != 'Currency' or amount_field.options != 'party_account_currency':
        return unavailable
    day = today()
    cutoff = add_days(day, -30)
    filters = {'docstatus': 1, 'is_return': 0, 'outstanding_amount': ['>', 0], 'posting_date': ['<=', day]}
    try:
        overdue = frappe.get_list('Sales Invoice', fields=['count(name) as invoice_count'],
                                 filters={**filters, 'posting_date': ['<=', cutoff]},
                                 order_by='', limit_page_length=0, ignore_permissions=False, user=user)
        groups = frappe.get_list('Sales Invoice', fields=['party_account_currency', 'sum(outstanding_amount) as amount', 'count(name) as invoice_count'],
                                filters=filters, group_by='party_account_currency', order_by='party_account_currency',
                                limit_page_length=0, ignore_permissions=False, user=user)
    except frappe.PermissionError:
        return unavailable
    totals, omitted = [], 0
    for group in groups:
        currency = group.get('party_account_currency')
        if not isinstance(currency, str) or not currency.strip() or currency != currency.strip():
            omitted += int(group['invoice_count'])
            continue
        amount = format(Decimal(str(group['amount'])), 'f')
        if '.' in amount:
            amount = amount.rstrip('0').rstrip('.')
        totals.append({'currency': currency, 'amount': amount})
    return {'available': True, 'date': day, 'cutoff_date': str(cutoff),
            'overdue_count': int(overdue[0]['invoice_count']) if overdue else 0,
            'receivables': totals, 'omitted_currency_count': omitted}
