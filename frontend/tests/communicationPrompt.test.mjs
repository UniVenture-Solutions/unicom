import assert from 'node:assert/strict'
import { communicationHint, followUpHint } from '../src/communicationPrompt.js'
const example='had a talk with Mohsin Sb, he is saying he will visit on Saturday'
assert.deepEqual(communicationHint(example),{channel:'',contact:'Mohsin Sb'})
for(const text of ['Will call Mohsin on Saturday','Planning a meeting','Need to discuss this','I did not call him','I never talked to him','We met the deadline','I called the API','We discussed the architecture'])assert.equal(communicationHint(text),null,text)
assert.deepEqual(communicationHint('Called Mohsin, he will visit Saturday'),{channel:'Call',contact:'Mohsin'})
assert.equal(communicationHint('Received an email from Mohsin, he confirmed').contact,'Mohsin')
assert.equal(communicationHint('Emailed the customer').channel,'Email')
assert.equal(communicationHint('Had a talk with Mohsin; will email the customer').channel,'')
assert.equal(followUpHint('I spoke with Mohsin on Monday, he will call next week','2026-11-19'),'')
assert.equal(followUpHint(example,'2026-11-19 10:00:00'),'2026-11-21')
assert.equal(followUpHint('Will visit next Saturday','2026-11-19'),'')
assert.equal(followUpHint('Will visit on Saturday','2026-11-21'),'')
assert.equal(followUpHint('Will visit Monday or Saturday','2026-11-19'),'')
assert.equal(followUpHint('Follow up due 2026-11-25','2026-11-19'),'2026-11-25')
assert.equal(followUpHint('Follow up due 2026-02-30','2026-11-19'),'')
assert.equal(followUpHint('Talked Saturday','2026-11-19'),'')
console.log('communication prompt detection checks passed')
