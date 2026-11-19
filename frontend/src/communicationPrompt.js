// Input is visible editor text, never HTML attributes or embedded URLs.
export function communicationHint(text) {
  const value = String(text || '').replace(/\s+/g, ' ').trim()
  // Match a completed interpersonal clause, not a future action or a technical verb.
  const clause = value.split(/[.;!?]|\b(?:will|going to|plan to|planning to)\b/i)[0]
  const completed = /\b(had (?:a )?(?:talk|call|meeting)|spoke|talked|called|met|discussed|emailed|sent (?:an? )?(?:email|message)|received (?:an? )?(?:email|message))\b/i
  if (!completed.test(clause) || /\b(?:not|never|haven't|hasn't|didn't|did not)\s+(?:yet\s+)?(?:spoken|talked|called|met|discussed|emailed|sent|received|had|call|meet|talk|discuss|email)\b/i.test(clause)) return null
  const person = /\b(?:with|to|from)\s+(?:[A-Z][a-z]+|him\b|her\b|them\b|the (?:customer|supplier|client|team)\b)/.test(clause) || /\b(?:[Cc]alled|[Mm]et|[Ee]mailed)\s+(?:[A-Z][a-z]+|him\b|her\b|them\b|the (?:customer|supplier|client|team)\b)/.test(clause)
  if (!person) return null
  const channel = /\b(?:emailed|sent (?:an? )?email|received (?:an? )?email)\b/i.test(clause) ? 'Email' : /\bwhatsapp\b/i.test(clause) ? 'WhatsApp' : /\b(?:called|had (?:a )?call)\b/i.test(clause) ? 'Call' : /\b(?:met|had (?:a )?meeting)\b/i.test(clause) ? 'Meeting' : ''
  const contact = clause.match(/\b(?:with|to|from|[Cc]alled|[Mm]et|[Ee]mailed)\s+([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|Sb))?)(?=[,.;!?]|\s+(?:and|he|she|they|about|regarding|on)\b|$)/)?.[1] || ''
  return { channel, contact }
}

// Use the saved site's calendar date; no browser timezone conversion or inferred time.
export function followUpHint(text, recordedAt) {
  const followUp = String(text || '').match(/\b(?:will|follow[ -]?up|next action|due)\b([\s\S]*)/i)?.[1]
  if (!followUp) return ''
  text = followUp
  const dates = [...new Set(text.match(/\b\d{4}-\d{2}-\d{2}\b/g) || [])]
  const weekdays = [...new Set((text.match(/\b(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b/gi) || []).map(day=>day.toLowerCase()))]
  if (dates.length + weekdays.length !== 1) return ''
  if (dates.length) {
    const date = new Date(dates[0]+'T12:00:00Z')
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0,10)===dates[0] ? dates[0] : ''
  }
  const base = String(recordedAt || '').slice(0,10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(base)) return ''
  const date = new Date(base+'T12:00:00Z')
  const day = ['sunday','monday','tuesday','wednesday','thursday','friday','saturday'].indexOf(weekdays[0])
  const delta = (day-date.getUTCDay()+7)%7
  // Same-day and "next Saturday" conventions are ambiguous: ask instead.
  if (!delta || /\bnext\s+(?:Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday)\b/i.test(text)) return ''
  date.setUTCDate(date.getUTCDate()+delta)
  return date.toISOString().slice(0,10)
}

export function createCommunicationDismissals(getStorage,namespace='communication') {
  const storageKey='unicom.'+namespace+'Dismissals.v1', limit=200
  let keys=[]
  try {
    const saved=JSON.parse(getStorage().getItem(storageKey) || '[]')
    if(Array.isArray(saved))keys=saved.filter(key=>typeof key==='string' && key.length<=2048).slice(-limit)
  } catch (_) { /* Storage can be disabled; keep dismissals in memory. */ }
  const keyFor=(user,issue,comment)=>JSON.stringify([user,issue,comment])
  return {
    has:(user,issue,comment)=>keys.includes(keyFor(user,issue,comment)),
    add(user,issue,comment){
      const key=keyFor(user,issue,comment)
      keys=[...keys.filter(value=>value!==key),key].slice(-limit)
      try{getStorage().setItem(storageKey,JSON.stringify(keys))}catch(_){}
    },
  }
}

export function savedCommunicationPrompts(issue,user,dismissals,visibleText,currentDate) {
  if(!user || user==='Guest' || !['Open','In Progress','Waiting'].includes(issue?.status))return {}
  const linked=new Set(issue.timeline.filter(event=>event.kind==='Communication').map(event=>event.source_comment).filter(Boolean)), prompts={}
  for(const event of [...issue.timeline].reverse()){
    if(event.kind!=='Comment' || event.actor!==user || linked.has(event.name) || dismissals.has(user,issue.name,event.name))continue
    const text=visibleText(event.body), hint=communicationHint(text)
    if(!hint)continue
    const date=followUpHint(text,event.recorded_at)
    prompts[event.name]={...hint,followUpDate:date && date>=currentDate ? date : ''}
  }
  return prompts
}


// A suggestion to confirm a plan, never evidence that a meeting happened.
export function plannedMeetingHint(text,recordedAt,currentDate='') {
  const value=String(text || '').replace(/\s+/g,' ').trim()
  const directive=value.match(/^follow[ -]?up\b[^.!?]*/i)?.[0]
  const clause=directive || value.match(/\b(?:meeting\s+(?:will|is going to)\s+be\s+(?:scheduled|held)|(?:will|going to|need to|plan to|planning to)\s+(?:schedule\s+(?:a\s+)?meeting|have\s+(?:a\s+)?meeting|meet\b|follow[ -]?up\b|call\b|visit\b)|follow[ -]?up\s+(?:on|due)\b)[^.!?]*/i)?.[0]
  if(!clause || /\b(?:not|never|cancelled|canceled|won't|completed|finished|done)\b/i.test(clause) || /\b(?:not|never|won't|didn't)\s*$/.test(value.slice(0,value.indexOf(clause))))return null
  const schedule_type=/\b(?:meeting|meet)\b/i.test(clause)?'Meeting':'Follow-up'
  const contact=clause.match(/\b(?:with|meet|call|visit)\s+([A-Z][a-z]+(?:\s+(?:[A-Z][a-z]+|Sb))?)(?=[,;]|\s+(?:on|at|and|about|regarding)\b|$)/)?.[1] || ''
  const date=followUpHint('will '+clause,recordedAt)
  const title=schedule_type==='Meeting' && !contact && /^meeting\s+(?:will|is going to)\s+be\s+(?:scheduled|held)\b/i.test(clause) ? 'Meeting' : clause.charAt(0).toUpperCase()+clause.slice(1,140)
  return {schedule_type,title,contact,scheduled_date:date && (!currentDate || date>=currentDate)?date:'',scheduled_time:''}
}

export function savedPlannedEventPrompts(issue,user,dismissals,visibleText,currentDate) {
  if(!user || user==='Guest' || !['Open','In Progress','Waiting'].includes(issue?.status))return {}
  const canDelegate=user==='Administrator' || user===issue.owner || user===issue.accountable_owner
  const eligible=new Set(issue.schedule_eligible_authors || [])
  const linked=new Set(issue.timeline.filter(event=>event.kind==='Scheduled').map(event=>event.source_comment).filter(Boolean)), prompts={}
  for(const event of issue.timeline){
    if(event.kind!=='Comment' || (event.actor!==user && !(canDelegate && eligible.has(event.actor))) || linked.has(event.name) || dismissals.has(user,issue.name,event.name))continue
    const hint=plannedMeetingHint(visibleText(event.body),event.recorded_at,currentDate)
    if(hint)prompts[event.name]=hint
  }
  return prompts
}
