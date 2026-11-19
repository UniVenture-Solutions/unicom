import assert from 'node:assert/strict'
import { plannedMeetingHint, savedPlannedEventPrompts, savedCommunicationPrompts,createCommunicationDismissals } from '../src/communicationPrompt.js'
const sample='meeting will be scheduled on saturday'
assert.equal(plannedMeetingHint(sample,'2026-11-19','2026-11-19').scheduled_date,'2026-11-21')
assert.equal(plannedMeetingHint(sample,'2026-11-19').title,'Meeting')
assert.equal(plannedMeetingHint('Followup with Hamza on stock return','2026-11-19').schedule_type,'Follow-up')
assert.equal(plannedMeetingHint('Followup with Hamza on stock return','2026-11-19').contact,'Hamza')
assert.equal(plannedMeetingHint('followup with hamza on stock return','2026-11-19').schedule_type,'Follow-up')
assert.equal(plannedMeetingHint('Followup with Hamza completed','2026-11-19'),null)
assert.equal(plannedMeetingHint(sample,'2025-11-19','2026-11-19').scheduled_date,'','historical date never rolls forward')
assert.equal(plannedMeetingHint('I will meet Mohsin on Saturday','2026-11-19').contact,'Mohsin')
assert.equal(plannedMeetingHint('I will follow up on 2026-11-20','2026-11-19').schedule_type,'Follow-up')
assert.equal(plannedMeetingHint('We will call Mohsin on Saturday','2026-11-19').scheduled_time,'')
for(const text of ['Had a meeting with Mohsin','I met Mohsin on Saturday','Meeting was scheduled on Saturday','I will not meet Mohsin','We will never meet Mohsin','I had a meeting, will email the report','The meeting is cancelled'])assert.equal(plannedMeetingHint(text,'2026-11-19'),null,text)
const dismissals=createCommunicationDismissals(()=>{throw Error('blocked')},'planned')
const source={name:'comment',kind:'Comment',actor:'me',body:sample,recorded_at:'2026-11-19'}
const issue={name:'issue',status:'Open',timeline:[source,{kind:'Communication',source_comment:'comment'}]}
assert.ok(savedPlannedEventPrompts(issue,'me',dismissals,x=>x,'2026-11-19').comment,'completed and planned link independent')
assert.deepEqual(savedPlannedEventPrompts({...issue,timeline:[...issue.timeline,{kind:'Scheduled',source_comment:'comment'}]},'me',dismissals,x=>x,'2026-11-19'),{})
assert.deepEqual(savedPlannedEventPrompts(issue,'other',dismissals,x=>x,'2026-11-19'),{})
assert.deepEqual(savedPlannedEventPrompts(issue,'',dismissals,x=>x,'2026-11-19'),{})
const completed={...source,body:'I called Mohsin, he will visit Saturday'}
assert.ok(savedCommunicationPrompts({...issue,timeline:[completed,{kind:'Scheduled',source_comment:'comment'}]},'me',dismissals,x=>x,'2026-11-19').comment,'scheduled log does not suppress completed communication suggestion')
console.log('planned event detection checks passed')

const importedComment={name:'source',kind:'Comment',actor:'waseem',body:'meeting will be scheduled on saturday',recorded_at:'2026-11-18 10:00:00'}
const delegated={name:'imported',status:'Open',owner:'nasir',accountable_owner:'owner',schedule_eligible_authors:['waseem'],timeline:[importedComment]}
assert.equal(savedPlannedEventPrompts(delegated,'nasir',dismissals,x=>x,'2026-11-19').source.title,'Meeting','creator sees exact imported screenshot comment')
assert.ok(savedPlannedEventPrompts(delegated,'owner',dismissals,x=>x,'2026-11-19').source,'accountable owner can review other author')
assert.ok(savedPlannedEventPrompts(delegated,'Administrator',dismissals,x=>x,'2026-11-19').source,'Admin can review eligible author')
assert.deepEqual(savedPlannedEventPrompts(delegated,'participant',dismissals,x=>x,'2026-11-19'),{},'ordinary participant cannot delegate')
assert.deepEqual(savedPlannedEventPrompts({...delegated,schedule_eligible_authors:[]},'nasir',dismissals,x=>x,'2026-11-19'),{},'disabled or access-revoked author not suggested')
