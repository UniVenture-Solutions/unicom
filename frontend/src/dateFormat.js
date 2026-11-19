const supported=new Set(['yyyy-mm-dd','dd-mm-yyyy','dd/mm/yyyy','dd.mm.yyyy','mm/dd/yyyy','mm-dd-yyyy'])

// Calendar components only: date-only values must never be shifted by a timezone.
export function formatDateOnly(value,format='yyyy-mm-dd') {
  if(value===null || value===undefined || value==='')return '—'
  const raw=String(value),match=raw.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if(!match)return raw
  const [,yyyy,mm,dd]=match,year=Number(yyyy),month=Number(mm),day=Number(dd)
  const leap=year%4===0 && (year%100!==0 || year%400===0)
  const days=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31]
  if(year<1 || month<1 || month>12 || day<1 || day>days[month-1])return raw
  return (supported.has(format)?format:'yyyy-mm-dd').replace(/yyyy|mm|dd/g,token=>({yyyy,mm,dd})[token])
}
