# HINDSIGHT

**Developer-controlled regression memory for AI-assisted coding.** HINDSIGHT turns
a reviewed historical bug into a bounded behavioral contract and reusable check,
so a future change can be evaluated against a known-good baseline.

AI-assisted edits can bring back behavior that was fixed before. A prose memory
or model confidence score cannot establish that a patch preserves that behavior.
HINDSIGHT makes the obligation explicit, binds it to reviewed source and evidence,
and keeps human approval separate from execution and reported outcomes.

This is the publication-safe source release. Original local evidence is excluded;
approved files, hash bindings and decisions remain preserved in the private
research workspace.

## Run the judge-facing demo

```sh
git clone https://github.com/YashwantC26/hindsight.git
cd hindsight
python3 -B -m http.server 8000 --bind 127.0.0.1 --directory dashboard/dist
```

Open **http://127.0.0.1:8000**. Python 3.10+ is the only requirement to serve the
static frontend. No npm install, backend, API key or model service is needed.
The dashboard reads a checksum-bound public summary at runtime and fails visibly
if it is missing or invalid. It replays retained results; it never executes candidates.

**VERIFIED_REAL_DEMO:** B PASS · R REGRESSION_DETECTED · N PASS. Nine invocations,
three stable repetitions per candidate, 108 assertions and 144 setup checks.
The retained original report SHA-256 is
`38d9b7e03bb9b3988bf1bdaa078e6b407fc729d55f5ce3618b8515e7c1e2ac6b`.

[90-second recording script](docs/DEMO_SCRIPT.md) ·
[Submission description](docs/SUBMISSION.md) ·
[Publication-safe evidence](docs/EVIDENCE_SUMMARY.md).

## How HINDSIGHT works

1. Identify one known buggy/fixed revision pair and preserve source provenance.
2. Have a developer review the finite behavioral contract and scenario recipe.
3. Generate a deterministic check and obtain separate exact-check approval.
4. Validate historical discrimination with repeated fresh-process evidence.
5. Activate the reviewed obligation through a separate developer decision.
6. Prepare inspected future candidates and require a new execution decision.
7. Reconstruct results from retained raw evidence rather than trusting summaries.

## What the MVP actually demonstrates

The subject is `cachetools.TLRUCache.__setitem__`. The approved contract checks
C1 expired-replacement membership absence, C2 target lookup raising KeyError,
C3 readability of an independently live survivor, and C4 valid-replacement
membership/readability. Four finite scenarios produce twelve assertions per run.

| Stage | Verified local state | Meaning |
| --- | --- | --- |
| Contract and exact check | Human approved | Specific bytes and finite obligations were reviewed. |
| Historical validation | Completed and accepted | Retained A/B/B/A/A/B evidence discriminates buggy and fixed revisions. |
| Checkpoint D | Effectively ACTIVE | The existing decision validates against current bindings. |
| Checkpoint E | VERIFIED_REAL_DEMO | Separately authorized run completed; retained evidence independently reviewed and read-only reverified. |
| Future candidate results | B PASS / R REGRESSION_DETECTED / N PASS | Three stable repetitions each; R fails precisely four C1/C2 scenario pairs. |

**INTENTIONALLY_SEEDED_REGRESSION:** R inserts an early return in the expired
replacement branch. It is deliberately seeded for demonstration and is not
evidence of autonomous discovery of a naturally occurring AI-generated bug.
N adds a setter docstring as a benign control. The real authorized execution
detected this deliberately seeded regression; it did not discover a naturally
occurring bug autonomously.

## Architecture and trust boundaries

Separate Python modules implement acquisition, bounded semantics, review,
deterministic generation, trusted collection, independent evidence validation,
activation and separately authorized future execution. SHA-256 pins bind reviewed
bytes; exact Git objects establish source identity. The worker executes immutable
verified buffers with fresh directories, isolated interpreter flags, controlled
environment, timeouts and bounded output. The parent checks raw streams, imports,
invocation identities, complete claims and stable observations.

Isolation flags are **not a hostile-code sandbox** or network isolation.
Candidates must be inspected and locally trusted. Reviewer identity and ledgers
are self-attestation rather than strong authentication or remote execution proof.
Checks before/after execution are not a cross-file transaction.
[Architecture details](docs/ARCHITECTURE.md).

## Reproduction

Python 3.10+ and the standard library are sufficient for the portable suites;
this release was tested with Python 3.14. No API key, model service, dependency
installation or upstream source download is required.

Run from the publication repository root:

```sh
python3 -B -m unittest discover -s HINDSIGHT/product_mvp -p 'test_checks.py' -v
python3 -B -m unittest discover -s HINDSIGHT/product_mvp -p 'test_lookup_classification.py' -v
python3 -B -m unittest discover -s HINDSIGHT/product_mvp -p 'test_public_worker.py' -v
```

These suites use synthetic mapping doubles and toy source buffers, never
historical A/B or real E candidates. Full activation/E tests need withheld local
approvals and evidence; they cannot be rerun from public source alone.
[Reproduction guide](docs/REPRODUCTION.md).

## Evidence and result interpretation

PASS establishes scoped assertions for the recorded run. A regression requires
complete, stable, independently eligible candidate evidence against a passing
baseline. ERROR, UNSTABLE and INCONCLUSIVE are ineligible for detection. Changed
or malformed bindings fail closed. No summary field overrides raw reconstruction.

[Public status](docs/status.json) and
[test results](docs/verification-results.json) are sanitized summaries,
not replacement approvals or portable proof that a public clone is ACTIVE.
The dashboard's data and manifest bind a derived summary, not public raw evidence.
Reviewer records, decisions, raw execution logs and complete upstream snapshots
are deliberately excluded. The actual human demo-v2 review packet stays local.

## Known limitations

One known case; upstream-test overlap; operator-proposed semantics; finite integer
fixtures; no autonomous discovery, unseen-bug generalization, universal correctness,
measured time saving or demonstrated commercial benefit. Earlier research failures
are not relabeled successes. An obsolete D test requires the activation decision
to be absent and reports a state-specific 39/40 result; current validity comes
from read-only verification. An older preservation receipt has one nonblocking
Finder metadata discrepancy; approved bindings and historical evidence still match.

## Technologies used

Python standard library, Git commit/tree/blob provenance, SHA-256, strict JSON,
deterministic templates, AST checks, unittest, bounded subprocess collection,
and POSIX exclusive atomic publication. The judge-facing dashboard is buildless
HTML, CSS and JavaScript using Web Crypto for summary checksums. It uses no
frontend framework, external fonts, analytics or remote API.

## Hackathon demo instructions

1. Launch the dashboard and use the [90-second script](docs/DEMO_SCRIPT.md).
2. Point out the seeded disclosure before describing the detected regression.
3. Inspect R's one-line patch and four exact scenario/claim failures.
4. Switch to B and N, then expand the stable execution order and provenance.
5. Explain separate human gates and the distinction between original local
   evidence and this public derived replay. Do not rerun candidates for the video.

Submit this GitHub URL, the commit and a short recording with disclosure and limits.

Dashboard checks (optional Node.js 20+ for JavaScript tests):

```sh
node --test tests/data.test.mjs
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
```

The private original evidence is needed only to regenerate the summary using
tools/export_demo.py. A fresh clone runs the already-generated dashboard and
portable tests without those originals. Full historical/E execution is intentionally
not a fresh-clone demo command.

HINDSIGHT source is MIT licensed. cachetools is separately MIT licensed; narrow
patch context is attributed in [NOTICE](NOTICE.md), with its license
retained. No complete cachetools implementation is vendored.

The public template suite omits the one original static API-conformance test that
requires full A/B snapshots. The omission is recorded in source-inventory.json;
its original local test and all approved implementation files remain unchanged.
