# Architecture and trust boundaries

HINDSIGHT is bounded to one reviewed cachetools obligation. It uses a deterministic
finite template rather than a generalized autonomous bug-finding pipeline.

```mermaid
flowchart LR
  S[Known source pair] --> C[Finite contract and recipe]
  C --> H[Human semantic review]
  H --> G[Deterministic check]
  G --> R[Separate exact-check review]
  R --> V[Historical evidence validation]
  V --> A[Separate human activation]
  A --> P[Future candidate preparation]
  P --> E[Separate execution decision]
  E --> X[Nine fresh B/R/N workers]
  X --> V2[Retained evidence reconstruction]
  V2 --> O[Private original report]
  O --> S2[Allowlisted public summary + checksum]
  S2 --> D2[Static dashboard replay]
```

Source provenance, semantic interpretation, conformance, human approval, historical
discrimination, activation and future execution are separate stages. Each binds
exact consumed bytes. A changed input invalidates downstream eligibility; mere
file presence is not proof of a currently valid decision.

Modules separate file primitives, acquisition, navigation, semantics, review,
generation, worker, collection, independent evidence validation, D activation and
E preparation/execution. D verifies eight helper hashes and loads immutable
buffers; E pins D's implementation. Public source copies preserve those exact
bytes without modifying or repinning approved code.

Claims: C1 expired target membership absence; C2 direct lookup KeyError; C3 live
survivor readability; C4 valid replacement membership/readability. Four scenarios
produce twelve assertions. Operator-proposed semantics and known upstream-test
exposure remain explicit limitations.

Parent verification checks strict JSON, complete scenarios/assertions, source and
import hashes, interpreter, collector command/PID/cwd, raw streams, transport/exit
codes and stable repetitions. ERROR cannot become detection. Decisions publish
exclusively and atomically; execution claims an exclusive attempt directory.
Partial failure consumes an attempt; retry needs a new preparation/authorization.

E's plan is B/R/N, N/R/B, B/R/N. Each of nine fresh workers has a ten-second
timeout, outer stdout/stderr limits 262144/65536 bytes, inner limits 32768/8192,
flags -I -S -B, controlled environment and fresh cwd. Snapshots are revalidated
before/after workers; cross-tree file aliases are rejected. The retained E run
is complete: B PASS, R REGRESSION_DETECTED, N PASS, with three stable repetitions
each. The dashboard is a presentation layer over a generated public summary;
it neither authorizes nor executes. Browser checks detect absent/changed/invalid
summary data against a committed manifest, not forged original execution.

Candidates must be locally trusted after inspection. Isolation flags are not a
hostile-code sandbox or network restriction. Interpreter/stdlib/Git are trusted
components. Identity, review time and ledgers are self-attestation. Verification
and publication do not continuously lock all inputs against concurrent writers.
No remote attestation, generalized proof, novelty or economic benefit is claimed.

The public clone omits local approvals and evidence and is not itself ACTIVE.
Local status is historically accepted, D ACTIVE, E VERIFIED_REAL_DEMO.
Public summaries document that state; they cannot independently certify it.
