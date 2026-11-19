import unittest
from types import SimpleNamespace
from unittest.mock import patch
from decimal import Decimal
import frappe
from unicom import monthly_dashboard as m

class MonthlyTests(unittest.TestCase):
 def setUp(self):
  self.calls=[];self.group_exists=True;self.leaves=True;self.companies=[frappe._dict(name='Company A',default_currency='PKR',default_finance_book='Default Book')]
  self.patchers=[patch.object(frappe,'get_installed_apps',return_value=['erpnext']),patch.object(frappe,'db',SimpleNamespace(exists=lambda *a:True)),patch.object(frappe,'has_permission',return_value=True),patch.object(m,'get_permitted_fields',side_effect=lambda dt,**kw:list({'Company':m.COMPANY_FIELDS|{'default_finance_book'},'Account':m.ACCOUNT_FIELDS,'Sales Invoice':m.SALES_FIELDS,'GL Entry':m.GL_FIELDS}[dt])),patch.object(m,'today',return_value='2026-11-20'),patch.object(frappe,'get_list',side_effect=self.query)]
  for p in self.patchers:p.start()
  self.addCleanup(lambda:[p.stop() for p in reversed(self.patchers)])
 def query(self,dt,**kw):
  self.calls.append((dt,kw));self.assertIs(kw['ignore_permissions'],False);self.assertEqual(kw['user'],'viewer')
  if dt=='Company':return self.companies
  if dt=='Sales Invoice':return [frappe._dict(company=c.name,amount=Decimal('-20.5')) for c in self.companies]
  if dt=='Account':
   if kw['filters']['is_group']==1:return [frappe._dict(name='Indirect group',lft=10,rgt=30)] if self.group_exists else []
   return [frappe._dict(name='Expense leaf')] if self.leaves else []
  if dt=='GL Entry':return [frappe._dict(total_debit=Decimal('100'),total_credit=Decimal('125.25'))]
 def test_signed_base_sales_and_net_credit_expense_with_exact_period(self):
  result=m.monthly_summary('viewer');self.assertEqual(result['sales']['items'][0]['amount'],'-20.5');self.assertEqual(result['expenses']['items'][0]['amount'],'-25.25')
  for dt,kw in self.calls:
   if dt in ('Sales Invoice','GL Entry'):self.assertEqual(kw['filters']['posting_date'],['between',['2026-11-01','2026-11-20']])
   if dt=='Sales Invoice':
    self.assertEqual(kw['filters']['docstatus'],1);self.assertEqual(kw['filters']['is_opening'],['!=','Yes']);self.assertNotIn('is_return',kw['filters']);self.assertIn({'SUM':'base_net_total','as':'amount'},kw['fields'])
   if dt=='GL Entry':
    self.assertEqual(kw['filters']['is_cancelled'],0);self.assertEqual(kw['filters']['is_opening'],'No');self.assertEqual(kw['filters']['voucher_type'],['!=','Period Closing Voucher']);self.assertEqual(kw['or_filters'],[['finance_book','in',['','Default Book']],['finance_book','is','not set']])
 def test_exact_nested_company_expense_group(self):
  m.monthly_summary('viewer');queries=[kw for dt,kw in self.calls if dt=='Account'];self.assertEqual(queries[0]['filters'],{'company':'Company A','account_name':'Indirect Expenses','root_type':'Expense','is_group':1});self.assertEqual(queries[1]['filters'],{'company':'Company A','root_type':'Expense','is_group':0,'lft':['>',10],'rgt':['<',30]})
 def test_missing_category_unavailable_distinct_from_empty_zero(self):
  self.group_exists=False;self.assertFalse(m.monthly_summary('viewer')['expenses']['items'][0]['available'])
  self.group_exists=True;self.leaves=False;item=m.monthly_summary('viewer')['expenses']['items'][0];self.assertTrue(item['available']);self.assertEqual(item['amount'],'0')
 def test_independent_read_and_field_denials(self):
  with patch.object(frappe,'has_permission',side_effect=lambda dt,**kw:dt!='GL Entry'):
   out=m.monthly_summary('viewer');self.assertFalse(out['expenses']['available']);self.assertTrue(out['sales']['available'])
  with patch.object(m,'get_permitted_fields',return_value=['name']):
   self.assertFalse(m.monthly_summary('viewer')['sales']['available'])
  with patch.object(frappe,'has_permission',return_value=False):
   self.assertFalse(m.monthly_summary('viewer')['expenses']['available'])
 def test_multiple_companies_keep_currency_and_zero_separate(self):
  self.companies.append(frappe._dict(name='Company B',default_currency='USD',default_finance_book=None));out=m.monthly_summary('viewer');self.assertEqual([i['currency'] for i in out['sales']['items']],['PKR','USD']);self.assertEqual(len(out['expenses']['items']),2)
 def test_no_visible_companies_never_invents_zero(self):
  self.companies=[];out=m.monthly_summary('viewer');self.assertFalse(out['sales']['available']);self.assertFalse(out['expenses']['available']);self.assertEqual([dt for dt,kw in self.calls],['Company'])

if __name__=='__main__':unittest.main()
