# Checkpoint E — frozen design v1

State: IMPLEMENTATION_IN_PROGRESS. This design authorizes no execution.

Scope is one existing activated contract, one unchanged approved check, exact fixed
baseline B (`c0fdf6abab38040947d6fe2e38c507401d5e2350`), and two inspected patches.
All additions live below checkpoint_e/. Checkpoints A–D, their decisions, snapshots,
source, templates and historical evidence remain byte-identical.

## Candidates and preparation

R is INTENTIONALLY_SEEDED_REGRESSION: insert an immediate return at the start of
the already-expired branch in TLRUCache.__setitem__. The existing deletion code
becomes unreachable for that branch. This single statement is deliberately
requested by the developer; it is neither historical A nor a naturally occurring
AI mistake. N is BENIGN_CONTROL: add a setter docstring explaining expiry-aware
assignment. It changes source meaningfully for readers without changing behavior.

Retain canonical unified diffs against B, a definition record with original/new
source SHA-256 and patch SHA-256, and authorship/disclosure. Apply only exact,
context-matching textual hunks to src/cachetools/__init__.py, using an in-process
parser; no patch scripts, shell commands, fuzz, alternate files or arbitrary paths.
Copy the complete 43-file verified B snapshot for each of B/R/N, preserving file
modes. Recompute Git blob IDs and SHA-256 manifests. Candidate revision identities
are explicitly synthetic tree digests, never claimed upstream commits. Compare
materialized files to B plus the declared patches on every preflight.

## Trust and authorization

Load activation_cli.py from its exact published, hash-verified source buffer. Its
existing source bootstrap verifies the eight approved helper modules. Reuse its
read-only verify_review and validate_decision gates; require effective ACTIVE.
Verify B's sole parent A through the existing Git/source gates. Bind the current
activation decision bytes, complete verification bindings, baseline identity,
candidate definitions/diffs/source manifests, execution plan and runner source
hash into a prepared bundle. External reviewer supplies exact bundle, activation
decision and runner pins; do not auto-fill them as human consent.

Authorization is a separate exclusive authorization.json with reviewer, positive
finite active minutes, explicit note, confirmation, time and complete current
bindings. It cannot be inferred from Checkpoint D. Write a complete fsynced staged
record, recheck bindings, then atomically hard-link without overwriting. Execution
additionally requires the exact authorization hash and an explicit execute flag.
The authorization permits one bounded execution directory only. An exclusive
directory claim blocks concurrency and retries, including after partial failure;
use a new prepared version and authorization to retry. Never repair old outputs.

## Execution and evidence

Plan is B/R/N, N/R/B, B/R/N: nine fresh processes, three per identity. Reuse the
unchanged historical_worker.py immutable-buffer execution path and the unchanged
historical_runner.capture_process collector, but not historical invocation or its
A/B evaluator. Supply candidate manifests and roots through the worker's existing
request interface. Verify snapshot paths/file sets/modes/hashes before and after
every process and revalidate ACTIVE/authorization. Run the same approved check
with -I -S -B, controlled environment, temporary cwd, ten-second timeout, 256 KiB
outer stdout / 64 KiB stderr limits, and existing 32 KiB / 8 KiB inner limits.

Each invocation retains request, launch context, independent collector metadata,
raw outer/inner streams and execution.json. Retain command, interpreter, worker,
PID, cwd, timestamps, transport, exit code, observations and all assertions. A
completed report pins the complete evidence file inventory; read-only verification
reconstructs contexts/requests, hashes, metadata and envelope validity before
recomputing classification. An existing summary or successful-looking status is
insufficient. Missing/partial evidence is ineligible; changed/duplicate/malformed
evidence is rejected. Read-only verification never launches or writes anything.

## Classification

PASS requires all three complete, stable candidate results and all assertions
PASS, with baseline PASS in all three repetitions. REGRESSION_DETECTED requires
baseline PASS, complete independent envelope validation, stable repeated candidate
observations and at least one approved-claim FAIL. ERROR includes setup, equality,
execution, timeout, output-limit and integrity failures; none counts as detection.
UNSTABLE means disagreement across otherwise valid repetitions. INCONCLUSIVE
means incomplete evidence or a baseline that fails an approved obligation. R's
expected C1/C2 pattern and N's expected PASS are stated as expectations only;
the summary is always calculated from retained observations. A demo success flag
also requires precisely those expected patterns, all controls passing, and N PASS.

## Limits and review gates

Candidates are locally trusted, developer-inspected Python. Isolation flags and
sanitized environment are not hostile-code containment or network isolation.
Local reviewer identity and ledgers are self-attestation, not authentication or
tamper-proof remote execution. Input verification and publication are not one
cross-file transaction. The same activated check overlaps a known upstream test;
this demonstrates reviewed obligation reuse, not discovery, novelty, universal
correctness, AI reliability, commercial benefit or generalization.

This implementation task performs only read-only live preflight, preparation,
static inspection and synthetic tests. No real E authorization and no real B/R/N
execution. Independent review and explicit developer authorization remain gates.
