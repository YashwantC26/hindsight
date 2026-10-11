"""Export an allowlisted presentation summary. Never authorize or execute code."""
import argparse
import hashlib
import json
from pathlib import Path

REPORT_SHA256 = '38d9b7e03bb9b3988bf1bdaa078e6b407fc729d55f5ce3618b8515e7c1e2ac6b'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Non-finite JSON')))


def derive(report_path, contract_path, patch_dir):
    raw = report_path.read_bytes()
    if sha(raw) != REPORT_SHA256:
        raise ValueError('Original report hash mismatch; no summary generated')
    report = strict_json(raw)
    bindings = report['bindings']
    contract_raw = contract_path.read_bytes()
    contract = strict_json(contract_raw)
    pins = bindings['activation']['verified']['trust_pins']
    if sha(contract_raw) != pins['contract_sha256']:
        raise ValueError('Approved contract hash mismatch')
    # Check the report-bound inputs consumed for this presentation, without running them.
    for relative, entry in report['evidence_inventory'].items():
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Unsafe inventory path')
        data = (report_path.parent / relative).read_bytes()
        if sha(data) != entry['sha256'] or len(data) != entry['size']:
            raise ValueError('Report-bound evidence mismatch')
    definitions = bindings['definitions']
    patches = {}
    for label in ('R', 'N'):
        data = (patch_dir / (label + '.patch')).read_bytes()
        if sha(data) != definitions['candidates'][label]['patch_sha256']:
            raise ValueError('Candidate patch mismatch')
        patches[label] = data.decode('utf-8')
    candidates = {}
    invocations = []
    for index, label in enumerate(bindings['plan']['order'], 1):
        envelope = strict_json((report_path.parent / f'invocation-{index:02}/execution.json').read_bytes())
        if envelope['label'] != label:
            raise ValueError('Invocation identity mismatch')
        scenarios = envelope['result']['scenarios']
        assertions = [a for s in scenarios for a in s['assertions']]
        setups = [a for s in scenarios for a in s['setup_evaluations'].values()]
        if envelope['status'] not in ('PASS', 'FAIL') or any(a['status'] != 'PASS' for a in setups):
            raise ValueError('Ineligible invocation')
        invocations.append({'index': index, 'label': label, 'repetition': envelope['repetition'],
                            'status': envelope['status'], 'assertions': len(assertions),
                            'passed_assertions': sum(a['status'] == 'PASS' for a in assertions),
                            'setup_checks': len(setups)})
        signatures = candidates.setdefault(label, {'signatures': [], 'runs': []})
        signatures['signatures'].append(json.dumps(scenarios, sort_keys=True))
        signatures['runs'].append(invocations[-1])
    classification = report['classification']
    for label, candidate in candidates.items():
        candidate['stable'] = len(set(candidate.pop('signatures'))) == 1
        candidate['status'] = classification['baseline'] if label == 'B' else classification['candidates'][label]['status']
        candidate['violations'] = [] if label == 'B' else classification['candidates'][label]['violations']
        candidate['source_sha256'] = definitions['baseline_source_sha256'] if label == 'B' else definitions['candidates'][label]['source_sha256']
        candidate['patch_sha256'] = None if label == 'B' else definitions['candidates'][label]['patch_sha256']
        candidate['diff'] = patches.get(label)
    # A small licensed excerpt, not an unpublished complete upstream snapshot.
    base_path = report_path.parent.parent / 'snapshots/B' / definitions['path']
    base = base_path.read_bytes()
    if sha(base) != definitions['baseline_source_sha256']:
        raise ValueError('Baseline source mismatch')
    lines = base.decode().splitlines()
    start = next(i for i, line in enumerate(lines) if i > 630 and 'with self.timer as time:' in line)
    candidates['B']['excerpt'] = '\n'.join(lines[start:start + 12])
    return {
        'schema_version': 1, 'state': 'VERIFIED_REAL_DEMO',
        'provenance': {'kind': 'PUBLIC_DERIVED_SUMMARY', 'report_sha256': REPORT_SHA256,
                       'contract_sha256': sha(contract_raw), 'check_sha256': pins['check_sha256'],
                       'runner_sha256': bindings['runner_sha256'],
                       'verification': 'COMPLETED_EVIDENCE_VERIFIED',
                       'independent_audit': 'Developer reports VERIFIED_REAL_DEMO; existing read-only verifier also passed',
                       'original_evidence_public': False, 'evidence_files': len(report['evidence_inventory']),
                       'scope': 'Summary derived from hash-pinned retained local originals; not remote execution attestation'},
        'contract': {'id': contract['contract_id'], 'version': contract['version'], 'subject': contract['subject'],
                     'claims': [{k: c[k] for k in ('id', 'display_text', 'scenario_ids')} for c in contract['claims']],
                     'exclusions': contract['exclusions']},
        'candidates': candidates, 'invocations': invocations,
        'totals': {'invocations': len(invocations), 'assertions': sum(r['assertions'] for r in invocations),
                   'setup_checks': sum(r['setup_checks'] for r in invocations),
                   'failed_assertions': sum(r['assertions'] - r['passed_assertions'] for r in invocations)},
        'plan': {k: bindings['plan'][k] for k in ('order', 'repetitions', 'timeout_seconds', 'flags',
                                                'stdout_limit', 'stderr_limit', 'check_stdout_limit', 'check_stderr_limit')},
        'demo_expectations_met': classification['demo_expectations_met'],
        'disclosure': report['limitations'][0], 'limitations': report['limitations'],
        'human_boundaries': ['Contract reviewed', 'Exact check approved', 'Checkpoint D activated',
                             'Separate E execution authorized', 'Bounded run completed'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--patch-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    summary = derive(args.report, args.contract, args.patch_dir)
    data = (json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    integrity = {'schema_version': 1, 'summary_sha256': sha(data), 'report_sha256': REPORT_SHA256}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'demo-data.json').write_bytes(data)
    (args.output_dir / 'integrity.json').write_text(json.dumps(integrity, indent=2) + '\n')
    print(json.dumps({'summary_sha256': sha(data), 'totals': summary['totals'],
                      'candidates': {k: v['status'] for k, v in summary['candidates'].items()}}))


if __name__ == '__main__':
    main()
