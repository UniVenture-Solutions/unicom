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
  if (!/\b(?:will|visit|follow[ -]?up|next action|due)\b/i.test(text)) return ''
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
