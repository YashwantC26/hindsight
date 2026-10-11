# Fresh-clone setup and safe reproduction

```sh
git clone https://github.com/YashwantC26/hindsight.git
cd hindsight
python3 -B -m http.server 8000 --bind 127.0.0.1 --directory dashboard/dist
```

Open http://127.0.0.1:8000. The checked-in dashboard runs immediately with Python;
it needs no build, install, model service or private fixture. Stop with Ctrl-C.
If port 8000 is busy, use another port and open the matching URL. Double-clicking
index.html is unsupported because the browser must fetch and validate the data.

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

Demo: use the dashboard and DEMO_SCRIPT.md. Disclose
INTENTIONALLY_SEEDED_REGRESSION; explain C1–C4; inspect the four R failures and
actual diff; show the nine retained invocations and original report hash. The
authorized real seeded demonstration is complete. Portable tests remain synthetic
and do not constitute another real candidate run.

The private local installation has exact snapshots, decisions and raw evidence.
Its verification also binds interpreter and object-source identity. This source
release supports inspection and synthetic reproduction, not portable replay of
private approval evidence. A new full chain requires new human review decisions
and separately authorized execution.

Presentation tests: node --test tests/data.test.mjs (Node.js 20+), then
python3 -B -m unittest discover -s tests -p 'test_*.py' -v.
These check summary consistency, failure handling and export rejection. Browser QA
also covers candidate switching, expanded details, laptop/mobile layout and missing,
changed and malformed summary data. See EVIDENCE_SUMMARY.md for trust limits.

The public template suite omits the one original static API-conformance test that
requires full A/B snapshots. The omission is recorded in source-inventory.json;
its original local test and all approved implementation files remain unchanged.
