// Presentation checks only. This is not a replacement for the trusted runner.
export const SUMMARY_REPORT_HASH='38d9b7e03bb9b3988bf1bdaa078e6b407fc729d55f5ce3618b8515e7c1e2ac6b';
export function validateSummary(data){
  const require=(condition,message)=>{if(!condition)throw new Error(`Invalid evidence summary: ${message}`);};
  require(data?.schema_version===1&&data.state==='VERIFIED_REAL_DEMO','schema or state');
  require(data.provenance?.kind==='PUBLIC_DERIVED_SUMMARY'&&data.provenance.report_sha256===SUMMARY_REPORT_HASH,'provenance');
  require(data.provenance.original_evidence_public===false,'original evidence scope');
  require(data.disclosure==='INTENTIONALLY_SEEDED_REGRESSION'&&data.limitations?.includes(data.disclosure),'seeded disclosure');
  require(Array.isArray(data.contract?.claims)&&data.contract.claims.length===4,'contract claims');
  require(Array.isArray(data.invocations)&&data.invocations.length===data.totals.invocations,'invocation count');
  require(data.invocations.reduce((n,r)=>n+r.assertions,0)===data.totals.assertions,'assertion count');
  require(data.invocations.reduce((n,r)=>n+r.setup_checks,0)===data.totals.setup_checks,'setup count');
  require(Array.isArray(data.plan?.order)&&data.plan.order.join('')===data.invocations.map(r=>r.label).join(''),'execution order');
  require(Array.isArray(data.human_boundaries)&&data.human_boundaries.length>0,'human boundaries');
  for(const label of ['B','R','N']){
    const c=data.candidates?.[label];require(c&&['PASS','REGRESSION_DETECTED'].includes(c.status),'candidate status');
    require(c.stable===true&&Array.isArray(c.runs)&&c.runs.length===data.plan.repetitions,'candidate stability');
    require(JSON.stringify(c.runs)===JSON.stringify(data.invocations.filter(r=>r.label===label)),'candidate repetitions');
    require(c.runs.every((r,i)=>r.repetition===i+1&&['PASS','FAIL'].includes(r.status)&&Number.isInteger(r.assertions)&&Number.isInteger(r.passed_assertions)&&r.passed_assertions>=0&&r.passed_assertions<=r.assertions),'invocation fields');
    require(Array.isArray(c.violations),'violations');
    require(c.status==='PASS'?c.violations.length===0&&c.runs.every(r=>r.status==='PASS'&&r.passed_assertions===r.assertions):c.violations.length>0&&c.runs.every(r=>r.status==='FAIL'&&r.passed_assertions<r.assertions),'status consistency');
    require(label==='B'?typeof c.excerpt==='string':typeof c.diff==='string','code context');
    for(const v of c.violations)require(data.contract.claims.some(c=>c.id===v.claim_id&&c.scenario_ids.includes(v.scenario_id))&&v.expected&&v.observed&&['value','KeyError'].includes(v.expected.kind)&&['value','KeyError'].includes(v.observed.kind),'claim mapping');
  }
}
