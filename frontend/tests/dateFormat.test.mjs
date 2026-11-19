import assert from 'node:assert/strict'
import {formatDateOnly} from '../src/dateFormat.js'
for(const [format,expected] of Object.entries({'yyyy-mm-dd':'2026-11-21','dd-mm-yyyy':'21-11-2026','dd/mm/yyyy':'21/11/2026','dd.mm.yyyy':'21.11.2026','mm/dd/yyyy':'11/21/2026','mm-dd-yyyy':'11-21-2026'}))assert.equal(formatDateOnly('2026-11-21',format),expected)
for(const blank of ['',null,undefined])assert.equal(formatDateOnly(blank,'dd/mm/yyyy'),'—')
assert.equal(formatDateOnly('2026-11-21',null),'2026-11-21')
assert.equal(formatDateOnly('2026-11-21','bogus'),'2026-11-21')
assert.equal(formatDateOnly('2024-02-29','dd.mm.yyyy'),'29.02.2024')
assert.equal(formatDateOnly('2026-02-29','dd/mm/yyyy'),'2026-02-29')
assert.equal(formatDateOnly('2026-11-21T00:00:00Z','dd/mm/yyyy'),'2026-11-21T00:00:00Z','timestamp excluded')
console.log('all six system date formats, fallback, blank and calendar checks passed')
