import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
import frappe
from unicom import dashboard


class ReceivablesTests(unittest.TestCase):
    def setUp(self):
        self.queries=[]
        self.field=SimpleNamespace(fieldtype='Currency',options='party_account_currency')
        self.patches=[patch.object(frappe,'get_installed_apps',return_value=['frappe','erpnext']),
                      patch.object(frappe,'db',SimpleNamespace(exists=lambda *args:True)),
                      patch.object(frappe,'has_permission',return_value=True),
                      patch.object(dashboard,'get_permitted_fields',return_value=list(dashboard.INVOICE_FIELDS)),
                      patch.object(frappe,'get_meta',return_value=SimpleNamespace(get_field=lambda field:self.field)),
                      patch.object(dashboard,'today',return_value='2026-11-20'),
                      patch.object(frappe,'get_list',side_effect=self.query)]
        for p in self.patches:p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])

    def query(self,doctype,**kwargs):
        self.queries.append((doctype,kwargs))
        if 'group_by' not in kwargs:return [{'invoice_count':2}]
        return [{'party_account_currency':'PKR','amount':Decimal('1234.500000'),'invoice_count':2},
                {'party_account_currency':'USD','amount':Decimal('10.2500'),'invoice_count':1},
                {'party_account_currency':None,'amount':Decimal('20'),'invoice_count':1}]

    def test_aggregates_are_permission_scoped_and_currencies_not_mixed(self):
        result=dashboard.receivables_summary('viewer')
        self.assertEqual(result,{'available':True,'date':'2026-11-20','cutoff_date':'2026-10-21','overdue_count':2,
                                 'receivables':[{'currency':'PKR','amount':'1234.5'},{'currency':'USD','amount':'10.25'}],
                                 'omitted_currency_count':1})
        self.assertEqual(len(self.queries),2)
        count,totals=[q[1] for q in self.queries]
        self.assertEqual(count['filters']['posting_date'],['<=','2026-10-21'])
        self.assertEqual(totals['filters']['posting_date'],['<=','2026-11-20'])
        for query in (count,totals):
            self.assertEqual(query['filters']['docstatus'],1)
            self.assertEqual(query['filters']['is_return'],0)
            self.assertEqual(query['filters']['outstanding_amount'],['>',0])
            self.assertIs(query['ignore_permissions'],False)
            self.assertEqual(query['user'],'viewer')
            self.assertEqual(query['limit_page_length'],0)
        self.assertEqual(totals['group_by'],'party_account_currency')
        self.assertIn({'SUM':'outstanding_amount','as':'amount'},totals['fields'])
        self.assertIn({'COUNT':'name','as':'invoice_count'},totals['fields'])
        self.assertEqual(count['fields'],[{'COUNT':'name','as':'invoice_count'}])

    def test_missing_app_read_or_required_field_access_returns_no_financial_data(self):
        for target,values in [('apps',[]),('read',False),('fields',['name','docstatus'])]:
            with self.subTest(target=target):
                manager=patch.object(frappe,'get_installed_apps',return_value=values) if target=='apps' else patch.object(frappe,'has_permission',return_value=values) if target=='read' else patch.object(dashboard,'get_permitted_fields',return_value=values)
                with manager:self.assertEqual(dashboard.receivables_summary('viewer'),{'available':False})
        self.assertEqual(self.queries,[])

    def test_empty_visible_dataset_does_not_invent_currency(self):
        with patch.object(frappe,'get_list',return_value=[]):result=dashboard.receivables_summary('viewer')
        self.assertEqual(result['overdue_count'],0)
        self.assertEqual(result['receivables'],[])
        self.assertEqual(result['omitted_currency_count'],0)

    def test_runtime_permission_denial_and_incompatible_currency_field_fail_closed(self):
        with patch.object(frappe,'get_list',side_effect=frappe.PermissionError):
            self.assertEqual(dashboard.receivables_summary('viewer'),{'available':False})
        self.field.options='currency'
        self.assertEqual(dashboard.receivables_summary('viewer'),{'available':False})

    def test_decimal_precision_is_preserved_without_float_or_fx_conversion(self):
        with patch.object(frappe,'get_list',side_effect=[[{'invoice_count':1}],[{'party_account_currency':'KWD','amount':Decimal('99999999999999.123456789'),'invoice_count':1}]]):
            result=dashboard.receivables_summary('viewer')
        self.assertEqual(result['receivables'],[{'currency':'KWD','amount':'99999999999999.123456789'}])
