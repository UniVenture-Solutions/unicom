"""Read-only representative sales and collections; all rows use native permissions."""
from decimal import Decimal
from urllib.parse import quote
import frappe
from frappe.utils import today, getdate, add_months
from unicom.monthly_dashboard import _readable, _list, _amount
from unicom.representative_dashboard import representative_summary


def _link(doctype,name):
    return '/desk/'+quote(doctype.lower().replace(' ','-'),safe='')+'/'+quote(name,safe='')


def _scope(user,name):
    if not isinstance(name,str) or not name or len(name)>140:frappe.throw('Not permitted',frappe.PermissionError)
    summary=representative_summary(user,representative=name)
    if not summary['available'] or len(summary['items'])!=1:frappe.throw('Not permitted',frappe.PermissionError)
    companies=_list('Company',user,fields=['name','default_currency'],order_by='name')
    return summary,{c.name:c.default_currency for c in companies}


def _invoice_access(user,fields):
    if not _readable('Sales Invoice',fields|{'product_representative','company','docstatus','posting_date'},user):return False
    meta=frappe.get_meta('Sales Invoice');link=meta.get_field('product_representative')
    return bool(link and link.fieldtype=='Link' and link.options=='Product Representative')


def _credit_access(user,extra=None):
    fields={'is_return','outstanding_amount','party_account_currency'}|(extra or set())
    if not _invoice_access(user,fields):return False
    field=frappe.get_meta('Sales Invoice').get_field('outstanding_amount')
    return bool(field and field.options=='party_account_currency')


def _credit_filters(name,companies,day):
    return {'product_representative':name,'company':['in',list(companies)],'docstatus':1,'posting_date':['<=',day],'is_return':0,'outstanding_amount':['>',0]}


def _bucket(due,day):
    if not due:return 'missing'
    days=(getdate(day)-getdate(due)).days
    return 'not_due' if days<=0 else '1_30' if days<=30 else '31_60' if days<=60 else '61_90' if days<=90 else '91_plus'


def detail_summary(user,name):
    summary,companies=_scope(user,name);day=summary['date'];first=day[:7]+'-01'
    result={'name':name,'label':summary['items'][0]['label'],'date':day,'start_date':first,'metrics':summary['items'][0],
            'trend':None,'ageing':None,'pipeline':{'delivery':None,'billing':None,'unpaid':None},'account':None}
    if not companies:return result
    if _invoice_access(user,{'is_opening','base_net_total'}):
        field=frappe.get_meta('Sales Invoice').get_field('base_net_total')
        if field and field.options=='Company:company:default_currency':
            try:
                start=str(add_months(first,-11));months=[str(add_months(first,n))[:7] for n in range(-11,1)]
                rows=_list('Sales Invoice',user,fields=['company','posting_date',{'SUM':'base_net_total','as':'amount'}],filters={'product_representative':name,'company':['in',list(companies)],'docstatus':1,'is_opening':['!=','Yes'],'posting_date':['between',[start,day]]},group_by='company,posting_date',order_by='')
                series={company:{month:Decimal(0) for month in months} for company,currency in companies.items() if currency}
                invalid=False
                for row in rows:
                    if row.company not in series:invalid=True;continue
                    series[row.company][str(row.posting_date)[:7]]+=Decimal(str(row.amount or 0))
                if not invalid:result['trend']=[{'company':company,'currency':companies[company],'points':[{'month':month,'amount':_amount(values[month])} for month in months]} for company,values in series.items()]
            except frappe.PermissionError:pass
    if _credit_access(user,{'due_date'}):
        try:
            rows=_list('Sales Invoice',user,fields=['company','party_account_currency','due_date',{'SUM':'outstanding_amount','as':'amount'},{'COUNT':'name','as':'count'}],filters=_credit_filters(name,companies,day),group_by='company,party_account_currency,due_date',order_by='')
            groups={};invalid=False
            for row in rows:
                currency=row.party_account_currency
                if not isinstance(currency,str) or not currency.strip() or currency!=currency.strip():invalid=True;continue
                key=(row.company,currency);groups.setdefault(key,{bucket:{'amount':Decimal(0),'count':0} for bucket in ['not_due','1_30','31_60','61_90','91_plus','missing']})
                bucket=groups[key][_bucket(row.due_date,day)];bucket['amount']+=Decimal(str(row.amount or 0));bucket['count']+=int(row.count)
            if not invalid:result['ageing']=[{'company':company,'currency':currency,'buckets':{key:{'amount':_amount(value['amount']),'count':value['count']} for key,value in buckets.items()}} for (company,currency),buckets in groups.items()]
        except frappe.PermissionError:pass
    order_fields={'product_representative','company','docstatus','transaction_date','status','per_delivered','per_billed'}
    if _readable('Sales Order',order_fields,user):
        field=frappe.get_meta('Sales Order').get_field('product_representative')
        if field and field.fieldtype=='Link' and field.options=='Product Representative':
            for key,fieldname in [('delivery','per_delivered'),('billing','per_billed')]:
                try:
                    rows=_list('Sales Order',user,fields=[{'COUNT':'name','as':'count'}],filters={'product_representative':name,'company':['in',list(companies)],'docstatus':1,'transaction_date':['<=',day],'status':['not in',['Closed','Cancelled','Completed','On Hold']],fieldname:['<',100]},order_by='')
                    result['pipeline'][key]=int(rows[0].count or 0) if rows else 0
                except frappe.PermissionError:pass
    if _credit_access(user,{'name'}):
        try:
            rows=_list('Sales Invoice',user,fields=[{'COUNT':'name','as':'count'}],filters=_credit_filters(name,companies,day),order_by='')
            result['pipeline']['unpaid']=int(rows[0].count or 0) if rows else 0
        except frappe.PermissionError:pass
    if _readable('Product Representative',{'name','account'},user) and _readable('Account',{'name','company','is_group'},user):
        try:
            reps=_list('Product Representative',user,fields=['account'],filters={'name':name},order_by='')
            account=reps[0].account if reps else None
            accounts=_list('Account',user,fields=['name','company'],filters={'name':account,'company':['in',list(companies)],'is_group':0},order_by='') if account else []
            if accounts:result['account']={'name':account,'url':_link('Account',account)}
        except frappe.PermissionError:pass
    return result


def transactions(user,name,kind='Sales Invoice',start=0,bucket=None,company=None,currency=None,period=None):
    summary,companies=_scope(user,name);day=summary['date']
    unavailable={'available':False,'items':[],'has_more':False}
    options={'Pending Delivery':('Sales Order','transaction_date','grand_total','currency'),'Pending Billing':('Sales Order','transaction_date','grand_total','currency'),'Sales Order':('Sales Order','transaction_date','grand_total','currency'),
             'Sales Invoice':('Sales Invoice','posting_date','grand_total','currency'),
             'Returns':('Sales Invoice','posting_date','grand_total','currency'),
             'Payment Entry':('Payment Entry','posting_date','paid_amount','paid_from_account_currency'),
             'Credit':('Sales Invoice','posting_date','outstanding_amount','party_account_currency')}
    if kind not in options or bucket not in (None,'','not_due','1_30','31_60','61_90','91_plus','missing'):frappe.throw('Invalid filter')
    try:start=max(0,min(int(start),10000))
    except (TypeError,ValueError):frappe.throw('Invalid page')
    selected_currency=currency
    if company and company not in companies:frappe.throw('Not permitted',frappe.PermissionError)
    if period not in (None,'','month') or (selected_currency and (not isinstance(selected_currency,str) or len(selected_currency)>140)):frappe.throw('Invalid filter')
    dt,date,amount,currency=options[kind]
    fields={'name','product_representative','company','docstatus',date,amount,currency,'status'}
    if dt=='Sales Invoice':fields.add('is_return')
    if dt=='Payment Entry':fields|={'payment_type','party_type'}
    if kind in ('Pending Delivery','Pending Billing'):fields|={'per_delivered','per_billed'}
    if kind=='Credit':fields|={'due_date','outstanding_amount','party_account_currency'}
    if not _readable(dt,fields,user):return unavailable
    meta=frappe.get_meta(dt);link=meta.get_field('product_representative');money=meta.get_field(amount)
    if not link or link.fieldtype!='Link' or link.options!='Product Representative' or not money or money.options!=currency:return unavailable
    filters={'product_representative':name,'company':['in',list(companies)],'docstatus':1,date:['<=',day]}
    if dt=='Payment Entry':filters.update(payment_type='Receive',party_type='Customer')
    if company:filters['company']=company
    if dt=='Sales Invoice':filters['is_return']=1 if kind=='Returns' else 0
    if kind in ('Pending Delivery','Pending Billing'):
        filters.update(status=['not in',['Closed','Cancelled','Completed','On Hold']])
        filters['per_delivered' if kind=='Pending Delivery' else 'per_billed']=['<',100]
    if kind=='Credit':
        filters.update(_credit_filters(name,companies,day))
        if company:filters['company']=company
        if selected_currency:filters['party_account_currency']=selected_currency
        if period=='month':filters['posting_date']=['between',[summary['start_date'],day]]
        if bucket=='missing':filters['due_date']=['is','not set']
        elif bucket=='not_due':filters['due_date']=['>=',day]
        elif bucket:
            from frappe.utils import add_days
            lower,upper={'1_30':(1,30),'31_60':(31,60),'61_90':(61,90),'91_plus':(91,None)}[bucket]
            filters['due_date']=['between',[add_days(day,-upper),add_days(day,-lower)]] if upper else ['<=',add_days(day,-lower)]
    party_field='party' if dt=='Payment Entry' else 'customer'
    party_allowed=_readable(dt,{party_field}|({'party_type'} if dt=='Payment Entry' else set()),user)
    outstanding_allowed=dt=='Sales Invoice' and _credit_access(user)
    selected=list(dict.fromkeys(['name','company',date,amount,currency,'status']+(['due_date'] if kind=='Credit' else [])+([party_field] if party_allowed else [])+(['outstanding_amount','party_account_currency'] if outstanding_allowed else [])))
    try:rows=frappe.get_list(dt,user=user,ignore_permissions=False,fields=selected,filters=filters,order_by=date+' desc, name desc',limit_start=start,limit_page_length=26)
    except frappe.PermissionError:return unavailable
    return {'available':True,'has_more':len(rows)>25,'items':[{'name':r.name,'doctype':dt,'date':str(r.get(date) or ''),'due_date':str(r.get('due_date') or ''),'status':r.status,'party':r.get(party_field) if party_allowed else '', 'outstanding':_amount(r.outstanding_amount) if outstanding_allowed and r.party_account_currency else None, 'outstanding_currency':r.get('party_account_currency') if outstanding_allowed else '', 'amount':_amount(r.get(amount)) if r.get(currency) else None,'currency':r.get(currency) or '', 'company':r.company,'url':_link(dt,r.name)} for r in rows[:25]]}
