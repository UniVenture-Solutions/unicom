"""Representative totals over native, current-user document and field permissions."""
from decimal import Decimal
import frappe
from frappe.utils import today
from unicom.monthly_dashboard import _readable, _list, _amount


def _report_totals(items, representatives):
    accounts={rep.name:rep.account for rep in representatives}
    result={}
    for key in ('sales','month_credit','total_credit','balance'):
        if any(item[key] is None for item in items):
            result[key]=None
            continue
        amounts={};seen=set()
        for item in items:
            if key=='balance':
                account=accounts.get(item['name'])
                if account in seen:continue
                seen.add(account)
            for entry in item[key]:
                group=(entry['company'],entry['currency'])
                amounts[group]=amounts.get(group,Decimal(0))+Decimal(entry['amount'])
        # Empty-currency zeros convey a real zero, never an unknown conversion.
        if any(currency for company,currency in amounts):
            amounts={group:amount for group,amount in amounts.items() if group[1] or amount!=0}
        result[key]=[{'company':company,'currency':currency,'amount':_amount(amount)} for (company,currency),amount in sorted(amounts.items())]
    return result


def representative_summary(user, representative=None):
    day=today();start=day[:7]+'-01'
    result={'available':False,'date':day,'start_date':start,'items':[],'totals':{key:None for key in ('sales','month_credit','total_credit','balance')}}
    if 'erpnext' not in frappe.get_installed_apps() or not _readable('Product Representative',{'name','full_name','account','status'},user):return result
    if not _readable('Company',{'name','default_currency'},user):return result
    link=frappe.get_meta('Product Representative').get_field('account')
    if not link or link.fieldtype!='Link' or link.options!='Account':return result
    try:
        reps=_list('Product Representative',user,fields=['name','full_name','account'],filters={'status':['!=','Inactive'],**({'name':representative} if representative else {})},order_by='full_name')
        companies=_list('Company',user,fields=['name','default_currency'],order_by='name')
    except frappe.PermissionError:return result
    company_map={row.name:row for row in companies}
    result.update(available=True,items=[{'name':r.name,'label':r.full_name or r.name,'sales':None,'month_credit':None,'total_credit':None,'balance':None} for r in reps])
    if not reps or not companies:return result
    names=[r.name for r in reps];items={r['name']:r for r in result['items']}
    representative_link=frappe.get_meta('Sales Invoice').get_field('product_representative')
    invoice_link_valid=bool(representative_link and representative_link.fieldtype=='Link' and representative_link.options=='Product Representative')
    common={'company':['in',list(company_map)],'product_representative':['in',names],'docstatus':1,'posting_date':['<=',day]}
    sales_fields={'company','product_representative','docstatus','posting_date','is_opening','base_net_total'}
    if invoice_link_valid and _readable('Sales Invoice',sales_fields,user):
        field=frappe.get_meta('Sales Invoice').get_field('base_net_total')
        if field and field.options=='Company:company:default_currency':
            try:
                rows=_list('Sales Invoice',user,fields=['product_representative','company',{'SUM':'base_net_total','as':'amount'}],filters={**common,'is_opening':['!=','Yes'],'posting_date':['between',[start,day]]},group_by='product_representative,company',order_by='')
                for item in items.values():item['sales']=[{'company':c.name,'currency':c.default_currency,'amount':'0'} for c in companies if c.default_currency]
                for row in rows:
                    currency=company_map[row.company].default_currency
                    if not currency:items[row.product_representative]['sales']=None;continue
                    cell=items[row.product_representative]['sales']
                    if cell is not None:
                        next(entry for entry in cell if entry['company']==row.company)['amount']=_amount(row.amount)
            except frappe.PermissionError:pass
    credit_fields={'company','product_representative','docstatus','posting_date','is_return','outstanding_amount','party_account_currency'}
    if invoice_link_valid and _readable('Sales Invoice',credit_fields,user):
        field=frappe.get_meta('Sales Invoice').get_field('outstanding_amount')
        if field and field.options=='party_account_currency':
            for key,dates in [('month_credit',['between',[start,day]]),('total_credit',['<=',day])]:
                try:
                    rows=_list('Sales Invoice',user,fields=['product_representative','company','party_account_currency',{'SUM':'outstanding_amount','as':'amount'}],filters={**common,'is_return':0,'outstanding_amount':['>',0],'posting_date':dates},group_by='product_representative,company,party_account_currency',order_by='')
                    for item in items.values():item[key]=[]
                    invalid=set()
                    for row in rows:
                        currency=row.party_account_currency
                        if not isinstance(currency,str) or not currency.strip() or currency!=currency.strip():invalid.add(row.product_representative);continue
                        items[row.product_representative][key].append({'company':row.company,'currency':currency,'amount':_amount(row.amount)})
                    for name,item in items.items():
                        if name in invalid:item[key]=None
                        elif not item[key]:item[key]=[{'company':'','currency':'','amount':'0'}]
                except frappe.PermissionError:pass
    gl_fields={'company','account','posting_date','is_cancelled','finance_book','debit','credit'}
    if (_readable('Company',{'name','default_currency','default_finance_book'},user) and _readable('Account',{'name','company','is_group'},user) and _readable('GL Entry',gl_fields,user)):
        try:
            books={row.name:row.default_finance_book for row in _list('Company',user,fields=['name','default_finance_book'],filters={'name':['in',list(company_map)]},order_by='')}
            accounts=_list('Account',user,fields=['name','company'],filters={'name':['in',list({r.account for r in reps if r.account}) or ['']],'company':['in',list(company_map)],'is_group':0},order_by='')
            account_map={a.name:a for a in accounts};balances={}
            for company in companies:
                account_names=[a.name for a in accounts if a.company==company.name]
                if not account_names or not company.default_currency or company.name not in books:continue
                default_books=['']+([books[company.name]] if books[company.name] else [])
                rows=_list('GL Entry',user,fields=['account',{'SUM':'credit','as':'total_credit'},{'SUM':'debit','as':'total_debit'}],filters={'company':company.name,'account':['in',account_names],'is_cancelled':0,'posting_date':['<=',day]},or_filters=[['finance_book','in',default_books],['finance_book','is','not set']],group_by='account',order_by='')
                totals={r.account:Decimal(str(r.total_credit or 0))-Decimal(str(r.total_debit or 0)) for r in rows}
                for account in account_names:balances[account]=[{'company':company.name,'currency':company.default_currency,'amount':_amount(totals.get(account,0))}]
            for rep in reps:
                if rep.account in account_map:items[rep.name]['balance']=balances.get(rep.account)
        except frappe.PermissionError:pass
    result['totals']=_report_totals(result['items'],reps)
    return result
