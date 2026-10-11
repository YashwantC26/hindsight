# HINDSIGHT

**Developer-controlled regression memory for AI-assisted coding.**

AI-assisted changes can reintroduce behavior that was already fixed. HINDSIGHT
turns a known historical bug into a developer-reviewed behavioral contract and an
exact approved check, then reuses that check to compare a future candidate against
a known-good baseline. Source hashes, retained process evidence and separate human
decisions keep interpretation, approval, execution and results distinct.

Our working MVP follows one cachetools TLRUCache regression through that complete
chain. In the authorized, retained Checkpoint E demonstration, the fixed baseline
passed, an intentionally seeded regression was detected, and a benign docstring
change passed. Nine fresh invocations produced three stable repetitions per
candidate, 108 assertions and 144 setup checks. Four distinct C1/C2 violations
showed an expired replacement leaving an old value present and readable.

The dashboard presents the actual derived results, candidate diff, claim failures,
stability and report hash. It uses a static HTML/CSS/JavaScript frontend served by
Python’s standard library: no install, backend, API key or model service is required
to run the judge-facing demo. The original Python system uses deterministic
templates, Git provenance, SHA-256, strict JSON and bounded fresh-process collection.

**INTENTIONALLY_SEEDED_REGRESSION:** the regression is deliberately seeded for
demonstration and is not evidence of autonomous discovery of a naturally occurring
AI-generated bug. Scope is one known case with upstream-test overlap and finite
fixtures. Candidates are locally trusted; isolation flags are not a hostile-code
sandbox. No unseen-bug generalization, universal correctness, measured productivity
gain or remote execution attestation is claimed. Public data is a derived summary;
private original evidence and approval records are excluded.

Repository: [github.com/YashwantC26/hindsight](https://github.com/YashwantC26/hindsight).
Launch and recording instructions are in the root README and DEMO_SCRIPT.md.
