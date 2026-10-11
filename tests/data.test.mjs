import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {validateSummary} from '../dashboard/dist/data.js';
const raw=readFileSync(new URL('../dashboard/dist/demo-data.json',import.meta.url));
const data=JSON.parse(raw);
test('actual exported summary matches committed checksum and validates',()=>{
  const integrity=JSON.parse(readFileSync(new URL('../dashboard/dist/integrity.json',import.meta.url)));
  assert.equal(createHash('sha256').update(raw).digest('hex'),integrity.summary_sha256);
  validateSummary(data);
});
test('all four exact report violations are mapped without deduplicating repetitions into assertions',()=>{
  assert.deepEqual(data.candidates.R.violations.map(v=>[v.scenario_id,v.claim_id]),[
    ['expiry_at_boundary','C1'],['expiry_at_boundary','C2'],['expiry_before_boundary','C1'],['expiry_before_boundary','C2']]);
  assert.equal(data.totals.failed_assertions,12);assert.equal(data.totals.assertions,108);assert.equal(data.totals.setup_checks,144);
});
for(const [name,change] of [
  ['source report pin',d=>d.provenance.report_sha256='0'.repeat(64)],
  ['missing candidate',d=>delete d.candidates.N],
  ['incomplete repetitions',d=>d.candidates.R.runs.pop()],
  ['forged success',d=>d.candidates.R.status='PASS'],
  ['incorrect totals',d=>d.totals.assertions++],
  ['missing seeded disclosure',d=>delete d.disclosure],
  ['unapproved claim',d=>d.candidates.R.violations[0].claim_id='C99'],
])test(`rejects ${name}`,()=>{const altered=structuredClone(data);change(altered);assert.throws(()=>validateSummary(altered));});
