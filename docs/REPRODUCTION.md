# Safe reproduction and hackathon demo

Use Python 3.10+ (tested on 3.14) and the standard library. No API credentials,
model service, cachetools installation or upstream download is needed.

From this publication repository's root:

```sh
python3 -B -m unittest discover -s HINDSIGHT/product_mvp -p 'test_checks.py' -v
python3 -B -m unittest discover -s HINDSIGHT/product_mvp -p 'test_lookup_classification.py' -v
python3 -B -m unittest discover -s HINDSIGHT/product_mvp -p 'test_public_worker.py' -v
```

Template tests cover deterministic generation, claim mapping, synthetic stale
values/survivor loss, API errors and refusal of implicit approvals. The lookup
matrix distinguishes successful returns, KeyError, equality compatibility and
evaluation errors. The worker subset copies seven original synthetic correction
tests: immutable buffers, source tampering, duplicate JSON, retained error streams,
sticky overflow and originless modules. None executes historical or E candidates.

checkpoint_e/test_runner.py is supplied for inspection but requires withheld
private approved fixtures. Use the listed portable suites, not broad discovery.
Public-clone activation/E verification must fail closed with missing evidence;
do not manufacture approvals to make it succeed.

Demo: show status.json; inspect complete R/N patches; disclose
INTENTIONALLY_SEEDED_REGRESSION; explain C1–C4; run synthetic suites; inspect the
validator/worker/gates; finish with the next human execution-review decision.
Do not claim a real future-patch result from these tests or from a seeded patch.

The private local installation has exact snapshots, decisions and raw evidence.
Its verification also binds interpreter and object-source identity. This source
release supports inspection and synthetic reproduction, not portable replay of
private approval evidence. A new full chain requires new human review decisions
and separately authorized execution.

The public template suite omits the one original static API-conformance test that
requires full A/B snapshots. The omission is recorded in source-inventory.json;
its original local test and all approved implementation files remain unchanged.
