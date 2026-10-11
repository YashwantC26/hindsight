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
| Checkpoint E | PREPARED_NOT_AUTHORIZED | demo-v2 source trees are inspected and bound; no E authorization or execution exists. |
| Future-patch result | NOT_OBSERVED | Expected candidate outcomes have not been measured in a real E run. |

**INTENTIONALLY_SEEDED_REGRESSION:** R inserts an early return in the expired
replacement branch. It is deliberately seeded for demonstration and is not
evidence of autonomous discovery of a naturally occurring AI-generated bug.
N adds a setter docstring as a benign control. No real future-patch regression
detection is claimed.

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
and POSIX exclusive atomic publication. No dashboard or orchestration framework
is needed for this MVP demonstration.

## Hackathon demo instructions

1. Explain the reviewed regression memory and separate human gates.
2. Show the four claims and [R/N patches](HINDSIGHT/product_mvp/checkpoint_e/candidates/).
3. Run the portable suites, labeling stale-value detection and the lookup matrix
   as synthetic demonstrations.
4. Show historical validation completed, D ACTIVE locally, E
   PREPARED_NOT_AUTHORIZED, and future outcomes NOT_OBSERVED.
5. Explain the next human gate: review demo-v2 and separately decide whether to
   authorize exactly nine processes. Stop before authorization or execution.

Submit the verified GitHub URL and commit, a short demo recording, the seeded
disclosure and current limitations. Actual E execution is a separate task, not
a prerequisite for honestly presenting this state.

HINDSIGHT source is MIT licensed. cachetools is separately MIT licensed; narrow
patch context is attributed in [NOTICE](NOTICE.md), with its license
retained. No complete cachetools implementation is vendored.

The public template suite omits the one original static API-conformance test that
requires full A/B snapshots. The omission is recorded in source-inventory.json;
its original local test and all approved implementation files remain unchanged.
