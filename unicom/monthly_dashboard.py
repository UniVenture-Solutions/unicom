"""Monthly company-base-currency summaries over the viewer's native permissions."""
from decimal import Decimal
import frappe
from frappe.model import get_permitted_fields
from frappe.utils import today

COMPANY_FIELDS={'name','default_currency'}
SALES_FIELDS={'company','docstatus','posting_date','is_opening','base_net_total'}
ACCOUNT_FIELDS={'name','account_name','company','root_type','is_group','lft','rgt'}
GL_FIELDS={'company','account','posting_date','is_cancelled','is_opening','voucher_type','finance_book','debit','credit'}


def _readable(doctype,fields,user):
    return bool(frappe.db.exists('DocType',doctype) and frappe.has_permission(doctype,ptype='read',user=user)
                and fields.issubset(get_permitted_fields(doctype,user=user,permission_type='read')))


def _amount(value):
    text=format(Decimal(str(value or 0)),'f')
    return text.rstrip('0').rstrip('.') if '.' in text else text


def _list(doctype,user,**kwargs):
    return frappe.get_list(doctype,user=user,ignore_permissions=False,limit_page_length=0,**kwargs)


def monthly_summary(user):
    day=today();start=day[:7]+'-01'
    result={'date':day,'start_date':start,'sales':{'available':False,'items':[]},'expenses':{'available':False,'items':[]}}
    if 'erpnext' not in frappe.get_installed_apps() or not _readable('Company',COMPANY_FIELDS,user):return result
    sales_allowed=_readable('Sales Invoice',SALES_FIELDS,user)
    expenses_allowed=(_readable('Company',COMPANY_FIELDS|{'default_finance_book'},user)
                      and _readable('Account',ACCOUNT_FIELDS,user) and _readable('GL Entry',GL_FIELDS,user))
    if not sales_allowed and not expenses_allowed:return result
    fields=['name','default_currency']+(['default_finance_book'] if expenses_allowed else [])
    try:companies=_list('Company',user,fields=fields,order_by='name')
    except frappe.PermissionError:return result
    if not companies:return result
    if sales_allowed:
        try:
            rows=_list('Sales Invoice',user,fields=['company',{'SUM':'base_net_total','as':'amount'}],
                       filters={'company':['in',[row.name for row in companies]],'docstatus':1,'is_opening':['!=','Yes'],
                                'posting_date':['between',[start,day]]},group_by='company',order_by='company')
            totals={row.company:row.amount for row in rows}
            result['sales']={'available':True,'items':[{'company':row.name,'currency':row.default_currency,
                 'available':bool(row.default_currency),'amount':_amount(totals.get(row.name)) if row.default_currency else None} for row in companies]}
        except frappe.PermissionError:pass
    if expenses_allowed:
        items=[]
        for company in companies:
            item={'company':company.name,'currency':company.default_currency,'available':False,'amount':None}
            if company.default_currency:
                try:
                    groups=_list('Account',user,fields=['name','lft','rgt'],filters={'company':company.name,'account_name':'Indirect Expenses','root_type':'Expense','is_group':1},order_by='name')
                    if len(groups)==1:
                        group=groups[0]
                        accounts=_list('Account',user,fields=['name'],filters={'company':company.name,'root_type':'Expense','is_group':0,'lft':['>',group.lft],'rgt':['<',group.rgt]},order_by='name')
                        debit=credit=Decimal(0)
                        if accounts:
                            books=['']+([company.default_finance_book] if company.default_finance_book else [])
                            entries=_list('GL Entry',user,fields=[{'SUM':'debit','as':'total_debit'},{'SUM':'credit','as':'total_credit'}],
                                filters={'company':company.name,'account':['in',[row.name for row in accounts]],'is_cancelled':0,'is_opening':'No',
                                         'voucher_type':['!=','Period Closing Voucher'],'posting_date':['between',[start,day]]},
                                or_filters=[['finance_book','in',books],['finance_book','is','not set']],order_by='')
                            if entries:
                                debit=Decimal(str(entries[0].total_debit or 0));credit=Decimal(str(entries[0].total_credit or 0))
                        item.update(available=True,amount=_amount(debit-credit))
                except frappe.PermissionError:pass
            items.append(item)
        result['expenses']={'available':True,'items':items}
    return result
