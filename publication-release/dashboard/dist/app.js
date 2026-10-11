import {validateSummary, SUMMARY_REPORT_HASH} from './data.js';

const $ = id => document.getElementById(id);
const titles = {B:'Known-good baseline',R:'Seeded regression',N:'Benign control'};
const contexts = {expiry_at_boundary:'expiry = now',expiry_before_boundary:'expiry < now',valid_replacement:'expiry > now',absent_target:'target initially absent'};
const explanations = {
  R:'The added return skips deletion of the previous live entry. At and before the expiry boundary, the target still exists and reads 5. That violates C1 (absence) and C2 (KeyError).',
  N:'Only the setter docstring changes. No executable statement changes; all approved claims pass in all three retained repetitions.',
  B:'The fixed baseline drops the previous entry when the incoming value is already expired. C1/C2 require absence and KeyError; C3/C4 protect the survivor and valid replacements.'
};
let summary;
function el(tag, className, text) { const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node; }
function value(observation) {return observation.kind==='KeyError'?'KeyError':JSON.stringify(observation.value);}

function select(label) {
  const candidate=summary.candidates[label];
  for(const card of $('candidates').children)card.setAttribute('aria-pressed',String(card.dataset.label===label));
  $('finding-title').textContent=candidate.violations.length?'The previous value survived.': 'Reviewed behavior preserved.';
  $('finding-count').textContent=candidate.violations.length?`${candidate.violations.length} DISTINCT VIOLATIONS`:'ALL CLAIMS PASS';
  $('findings').replaceChildren();
  if(candidate.violations.length) {
    const table=el('table','findings-table');
    const head=el('thead');const row=el('tr');
    for(const title of ['Scenario / claim','Expected','Observed']){const th=el('th','',title);th.scope='col';row.append(th);}head.append(row);table.append(head);
    const body=el('tbody');
    for(const v of candidate.violations){
      const tr=el('tr');const name=el('td');name.append(el('span','claim-tag',v.claim_id),el('span','',contexts[v.scenario_id]||v.scenario_id),el('span','scenario',v.scenario_id));
      tr.append(name,el('td','',value(v.expected)),el('td','observed',value(v.observed)));body.append(tr);
    }table.append(body);$('findings').append(table);
    $('finding-note').textContent=`Each pair fails in ${candidate.runs.length} stable repetitions. C3 and C4 remain passing controls.`;
  } else {
    const list=el('div','pass-claims');
    for(const claim of summary.contract.claims){const item=el('div','pass-claim');item.append(el('b','',claim.id),el('span','',claim.display_text));list.append(item);}
    $('findings').append(list);$('finding-note').textContent=`${candidate.runs.reduce((sum,r)=>sum+r.passed_assertions,0)} / ${candidate.runs.reduce((sum,r)=>sum+r.assertions,0)} assertions pass across ${candidate.runs.length} stable repetitions.`;
  }
  $('change-title').textContent=label==='B'?'Fixed upstream behavior':`${label} · ${label==='R'?'one early return':'docstring only'}`;
  $('code-diff').replaceChildren();
  for(const line of (candidate.diff||candidate.excerpt).split('\n')){
    if(!line && candidate.diff)continue;
    const type=line.startsWith('+')&&!line.startsWith('+++')?'diff-add':line.startsWith('@@')?'diff-context':line.startsWith('---')||line.startsWith('+++')?'diff-header':'';
    $('code-diff').append(el('span',type,line||' '));
  }
  $('change-explanation').textContent=explanations[label];
}

function render(data) {
  summary=data;
  $('metrics').replaceChildren();
  for(const [key,label] of [['invocations','invocations'],['assertions','assertions'],['setup_checks','setup checks']]){const metric=el('span');metric.append(el('b','',String(data.totals[key])),el('span','',label));$('metrics').append(metric);}
  $('candidates').replaceChildren();
  for(const label of ['B','R','N']){
    const c=data.candidates[label], card=el('button',`candidate ${c.status==='REGRESSION_DETECTED'?'regression':''}`);
    card.type='button';card.dataset.label=label;card.setAttribute('aria-pressed','false');
    const head=el('div','card-head'),name=el('div','candidate-label');name.append(el('span','letter',label),el('span','',label==='B'?'BASELINE':'CANDIDATE'));
    head.append(name,el('span','outcome',c.status));card.append(head,el('h3','',titles[label]));
    const foot=el('div','card-foot'),reps=el('div','repetitions');for(const r of c.runs)reps.append(el('span','rep',String(r.repetition)));
    reps.append(el('span','stability',`${c.runs.length} stable repetitions`));foot.append(reps,el('span','',`${c.runs.reduce((n,r)=>n+r.passed_assertions,0)}/${c.runs.reduce((n,r)=>n+r.assertions,0)} pass`));card.append(foot);
    card.addEventListener('click',()=>select(label));$('candidates').append(card);
  }
  $('report-hash').textContent=data.provenance.report_sha256;
  $('claims').replaceChildren();
  for(const c of data.contract.claims){const p=el('p');p.append(el('code','',c.id),el('span','',` · ${c.display_text}`));$('claims').append(p);}
  $('run-order').replaceChildren();
  for(const r of data.invocations){const pill=el('span',`run-step ${r.label==='R'?'regression':''}`,`${String(r.index).padStart(2,'0')} ${r.label} · ${r.status}`);$('run-order').append(pill);}
  $('run-limits').textContent=`${data.plan.repetitions} repetitions per candidate · ${data.plan.timeout_seconds}s per process · ${data.plan.flags.join(' ')}. Outer stdout/stderr caps ${data.plan.stdout_limit}/${data.plan.stderr_limit} bytes; inner caps ${data.plan.check_stdout_limit}/${data.plan.check_stderr_limit} bytes.`;
  $('boundaries').replaceChildren(...data.human_boundaries.map(t=>el('li','',t)));
  $('verification-state').textContent='VERIFIED REAL DEMO';$('verification-state').classList.remove('error');
  $('error').hidden=true;$('results').hidden=false;
  select(data.candidates.R.status==='REGRESSION_DETECTED'?'R':'B');
}

async function load() {
  $('results').hidden=true;$('error').hidden=true;$('verification-state').textContent='Loading evidence…';
  try {
    const [dataResponse,integrityResponse]=await Promise.all([fetch('./demo-data.json',{cache:'no-store'}),fetch('./integrity.json',{cache:'no-store'})]);
    if(!dataResponse.ok||!integrityResponse.ok)throw new Error('The public evidence data or integrity manifest is missing.');
    const bytes=await dataResponse.arrayBuffer(),integrity=await integrityResponse.json();
    if(integrity.report_sha256!==SUMMARY_REPORT_HASH)throw new Error('The source report pin does not match this reviewed demo.');
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    if(hash!==integrity.summary_sha256)throw new Error('The public evidence summary checksum does not match.');
    const data=JSON.parse(new TextDecoder().decode(bytes));validateSummary(data);render(data);
  }catch(error){
    $('results').hidden=true;$('error').hidden=false;$('verification-state').textContent='EVIDENCE UNAVAILABLE';$('verification-state').classList.add('error');
    $('error-message').textContent=error instanceof Error?error.message:'Invalid evidence data.';
  }
}
$('retry').addEventListener('click',load);
$('copy-hash').addEventListener('click',async()=>{
  try{await navigator.clipboard.writeText(summary.provenance.report_sha256);$('copy-hash').textContent='Copied';}catch{$('copy-hash').textContent='Select hash';}
});
load();
