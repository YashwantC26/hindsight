# Publication audit and scope

The publication repository is a separately reviewed source export. It does not
inherit the research repository's Git history, which includes machine paths,
third-party author contacts and private generated artifacts in reachable objects.
Sanitizing a tip commit or adding ignore rules would not remove those objects.
Original history and local evidence are preserved rather than rewritten.

The allowlist contains implementation source, deterministic templates and schemas,
candidate definitions and the two narrow patches, synthetic tests, source hashes,
new documentation and sanitized status/test summaries. Implementation source is
copied byte-identically. The template test export explicitly omits one static
API-conformance case requiring private full snapshots. The seven worker tests
are an original synthetic class extracted without private fixture imports.
source-inventory.json records both transformations; approved originals are unchanged.

Excluded: raw research/planning archives, reviewer decisions and notes, activation
record, review packets containing personal paths, all raw invocation/inference
logs, preservation inventories, local interpreter manifests, all 344 duplicate
snapshot files, the restored bare upstream Git repository, environment files,
virtual environments, caches, Finder metadata and bytecode. Full cachetools trees
are not necessary for this publication's synthetic reproduction. Narrow patch
context is attributed and its MIT license retained.

All proposed files were read and screened for provider credential formats,
private keys, literal credential assignments, contact data, machine/temporary
paths, prohibited generated directories, symlinks, NUL/binary content and size.
Credential words and artificial reviewer fields in source/test code were inspected
as code, not exported real credentials or developer decisions. No detected live
credentials or private reviewer values are included. This is a bounded audit,
not a claim that regex screening can prove the absence of every possible secret.

The local installation was read-only verified as D ACTIVE and E
PREPARED_NOT_AUTHORIZED; 203 approved bindings and 49 historical evidence files
verified. Nine real candidate processes were not run and no E authorization was
created. Portable tests and local synthetic suites are recorded separately.
The public clone deliberately lacks approval evidence and is not ACTIVE itself.

The older preservation receipt comparison is 620/621 due solely to ancillary
Finder metadata. That discrepancy is preserved and disclosed; it is not silently
repaired or restated as a current 621/621 claim. The obsolete D absence assertion
is separate from current read-only decision validation.

A GitHub target has not yet been verified: the supplied repository URL is a
placeholder. No visibility change, remote creation, force push or history overwrite
is permitted. Publishing requires a real existing GitHub URL, authenticated access,
and an empty or compatible target history. Unrelated remote history blocks a push.

The local publication commit uses an explicitly non-personal publication identity,
not a fabricated reviewer identity. It is not a signed human approval. The original
repository's index and research history are not replaced by this export.
