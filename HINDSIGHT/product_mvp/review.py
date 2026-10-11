"""Evidence preparation and explicit semantic review; never approves on prepare."""
import json
from pathlib import Path

from common import BUGGY, FIXED, PRODUCTION, REPOSITORY, canonical, now, read, sha, write, write_bytes
from navigation import analyze
from semantics import contract_draft, corrections, recipe_draft, validate_review_metadata, validate_semantics
from snapshots import git, verify_acquisition


def require_reference_gate(run):
    verify_acquisition(run)
    results = read(run / "reference-results.json")
    expected_order = [(i, label) for i, pair in enumerate((("A", "B"), ("B", "A"), ("A", "B")), 1) for label in pair]
    actual_order = [(r["pair"], r["label"]) for r in results["runs"]]
    if not results["accepted"] or actual_order != expected_order:
        raise ValueError("CHECKPOINT_A_NOT_PASSED")
    for result in results["runs"]:
        expected = "FAIL" if result["label"] == "A" else "PASS"
        worker = result["worker"]
        if (result["status"] != expected or worker["status"] != expected or worker["tests_run"] != 1
                or worker["errors"] != 0 or worker["skipped"] != 0
                or worker["failures"] != (1 if result["label"] == "A" else 0)
                or result["exit_code"] != (1 if result["label"] == "A" else 0)
                or not worker.get("imports_before") or not worker.get("imports_after")):
            raise ValueError("CHECKPOINT_A_INVALID_RESULT")
    return results


def review_hashes(run):
    return {"bundle_sha256": sha((run / "review-bundle.json").read_bytes()),
            "evidence_sha256": sha((run / "evidence/evidence.json").read_bytes()),
            "contract_sha256": sha((run / "review/contract.json").read_bytes()),
            "recipe_sha256": sha((run / "review/recipe.json").read_bytes())}


def verify_review(run):
    require_reference_gate(run)
    bundle = read(run / "review-bundle.json")
    for name, expected in bundle["immutable_files"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("INVALID_REVIEW_BUNDLE_PATH")
        if (run / path).is_symlink() or sha((run / path).read_bytes()) != expected:
            raise ValueError("IMMUTABLE_REVIEW_INPUT_CHANGED: " + name)
    diff = (run / "evidence/production.diff").read_text()
    analysis = analyze(run, diff)
    if canonical(analysis) != canonical(read(run / "evidence/analysis.json")):
        raise ValueError("SOURCE_ANALYSIS_CHANGED")
    for label in ("A", "B"):
        if (run / f"evidence/production-{label}.py").read_bytes() != (run / "snapshots" / label / PRODUCTION).read_bytes():
            raise ValueError("EVIDENCE_SOURCE_SNAPSHOT_MISMATCH")
    checkpoint = run / "checkpoint-b.json"
    if checkpoint.exists():
        record = read(checkpoint)
        if (sha((run / "review/REVIEW_PACKET.md").read_bytes()) != record["review_packet_sha256"]
                or sha((run / "review-bundle.json").read_bytes()) != record["bundle_sha256"]):
            raise ValueError("PREPARED_REVIEW_PACKET_OR_BUNDLE_CHANGED")
    return review_hashes(run)


def render_packet(run, evidence, analysis, contract, recipe, hashes):
    lines = ["# Checkpoint B: semantic review", "", "**DRAFT — not approved. No executable product check has been generated.**", "",
             "This is an operator-proposed, reference-assisted contract for one known cachetools fix.",
             "No fresh isolated semantic model was called; model-proposal quality is NOT_EVALUATED.",
             "The existing upstream test already covers the core obligation. No novelty or autonomous recovery is claimed.", "",
             "## Your decision", "",
             "Inspect the source, proposed clauses, and recipe below. Approve them, request edits, or reject.",
             "Approval of the architecture/implementation task is not semantic approval of these artifacts.",
             "C1–C4 and the precondition kinds are normative. Explanatory display text/notes can be edited;",
             "unsupported changes to normative predicates or the exact MVP fixture values block this finite template.",
             "Every edit is preserved against the original draft and requires approval of the new exact hashes.", "",
             "| Artifact | Exact SHA-256 |", "| --- | --- |"]
    lines += [f"| {key} | `{value}` |" for key, value in hashes.items()]
    lines += ["", "This packet displays the original prepared draft. If you edit review/contract.json or review/recipe.json,",
              "run `status` to see the current hashes; the frozen original packet does not silently change.", "",
              "## Historical identity and feasibility", "", f"Repository: {REPOSITORY}", "",
              f"A: `{BUGGY}`. B: `{FIXED}`. Single direct parent verified from Git objects.", "",
              "Unchanged fixed upstream test: FAIL A / PASS B in all three fresh-process pairs (A/B, B/A, A/B).",
              "Same-process import-origin/hash verification and complete snapshot-byte verification passed.",
              "This is reference feasibility only. The original research-generated check remains ERROR/ERROR.", "",
              "## Proposed public behavior", "",
              "Given a target entry still readable at time 10, overwriting it with an incoming value whose fixture",
              "expiry is at or before 10 must remove public access to that key. The incoming expiry is not the old entry's expiry.", "",
              "| Claim | Normative predicate | Explanation | Scenario scope | Origin |", "| --- | --- | --- | --- | --- |"]
    lines += [f"| {c['id']} | `{c['predicate']}` | {c['display_text']} | {', '.join(c['scenario_ids'])} | {c['origin']} |" for c in contract["claims"]]
    lines += ["", "Preconditions apply to the listed scenarios; the expired condition is not a precondition of the valid-replacement control.", "",
              "| Precondition | Scenario scope |", "| --- | --- |"]
    lines += [f"| {p['kind']} | {', '.join(p['scenario_ids'])} |" for p in contract["preconditions"]]
    lines += ["",
              "Exclusions: " + ", ".join(contract["exclusions"]) + ".", "",
              "## Entity definitions and origins", "",
              "SOURCE_LOCATED means syntax was located in exact source. The semantic labels below are operator interpretations,",
              "not mechanical proofs. Full exact citations for both revisions are in evidence/analysis.json.", "",
              "| Entity (fixed B) | Source expression | Origin expression | Source lines |", "| --- | --- | --- | --- |"]
    for entity in analysis["entities"]["B"]:
        c = entity["citation"]
        lines.append(f"| {entity['id']} | `{entity['source_expression']}` | `{entity['origin_expression']}` | {c['start_line']}–{c['end_line']} |")
    lines += ["", "## Scenario recipe", "",
              "All scenarios use a fresh TLRUCache(maxsize=2), constant timer 10, and constructor-supplied callback `now + incoming_value`.",
              "Target key 1 initially has value 5 when present (expiry 15); survivor key 2 has value 7 (expiry 17).",
              "The old entry and survivor are confirmed readable before replacement. Setup violations will be ERROR, not detection.", "",
              "| Scenario | Target initially present | Incoming value / expiry | Expected target | Claims | Role |", "| --- | --- | --- | --- | --- | --- |"]
    for scenario in recipe["scenarios"]:
        lines.append(f"| {scenario['id']} | {scenario['initial_target_present']} | {scenario['replacement']} / {10 + scenario['replacement']} | {scenario['expected_target']} | {', '.join(scenario['claim_ids'])} | {scenario['historical_role']} |")
    lines += ["", "Membership and direct target lookup must be observed before cleanup-triggering size/iteration operations.",
              "The template will not use len, currsize, private storage, monkeypatching, real sleep, network, or property assignment.", "",
              "## Uncertainties and approval boundaries", "",
              "- AST retrieval does not prove the behavioral interpretation or complete semantic coverage.",
              "- Cross-method meaning of the previous value and callback behavior require reviewer judgment.",
              "- Finite integer scenarios do not prove concurrency, arbitrary callbacks, or universal cache correctness.",
              "- API syntax is available; the new product check has not been generated or executed.",
              "- Review has not occurred; reviewer identity, corrections, and active review time are unrecorded.",
              "- This known case has existing test coverage; added value is traceability, review, and reuse workflow, not a novel oracle.", "",
              "## Exact production change", "", "```diff", (run / "evidence/production.diff").read_text().rstrip(), "```", "",
              "## Relevant exact definitions", "",
              "Complete original modules and full symbol maps remain available in evidence/ and snapshots/. Excerpts below retain exact source lines."]
    snippets = [("A", "TLRUCache.__setitem__"), ("B", "TLRUCache.__setitem__"),
                ("B", "TLRUCache.__init__"), ("B", "TLRUCache.ttu"),
                ("B", "TLRUCache.__contains__"), ("B", "TLRUCache.__getitem__"),
                ("B", "Cache.__getitem__"), ("B", "Cache.__missing__"),
                ("B", "_TimedCache._Timer.__enter__")]
    for label, name in snippets:
        symbol = analysis["symbols"][label][name]
        lines += ["", f"### {label}: {name}, lines {symbol['start_line']}–{symbol['end_line']}", "",
                  "```python", symbol["quote"].rstrip(), "```"]
    lines += ["", "## Existing upstream-test overlap (separate reference semantics)", "",
              "The following unchanged fixed upstream test was used for feasibility. It supplies known reference semantics;",
              "it is not a model proposal or a repaired research witness. It also checks size/iteration, which this MVP excludes.", "",
              "```python", analysis["reference"]["quote"].rstrip(), "```", "",
              "The recipe extends the finite fixture with a negative-expiry example and a live-survivor observation.",
              "That does not establish useful new coverage; the central expired-overwrite behavior is already tested upstream.", "",
              "## Machine-readable artifacts", "",
              "- evidence/evidence.json: revision, blob, source, diff and reference provenance.",
              "- evidence/analysis.json: definition ranges/byte offsets, entity citations, local calls and changed hunk mapping.",
              "- drafts/: unchanged original operator proposals; review/: editable copies for your decision.",
              "- model-proposal-status.json: fresh proposal NOT_RUN, quality NOT_EVALUATED.", "",
              "Reply with approval of these exact contract/recipe hashes, your reviewer name, and active review minutes,",
              "or specify corrections/rejection. Checkpoint C will separately require approval of exact emitted check bytes.", ""]
    return "\n".join(lines)


def prepare_review(run):
    require_reference_gate(run)
    if (run / "review-bundle.json").exists():
        raise ValueError("Review already prepared; do not overwrite the attempt")
    acquisition = read(run / "acquisition.json")
    repository = Path(acquisition["local_object_source"])
    production_diff = git(repository, "diff", "--no-ext-diff", "--no-textconv", "--no-renames", BUGGY, FIXED, "--", PRODUCTION)
    changed = git(repository, "diff", "--name-status", "--no-ext-diff", "--no-textconv", "--no-renames", BUGGY, FIXED).decode()
    write_bytes(run / "evidence/production.diff", production_diff)
    for label in ("A", "B"):
        write_bytes(run / f"evidence/production-{label}.py", (run / "snapshots" / label / PRODUCTION).read_bytes())
    analysis = analyze(run, production_diff.decode())
    write(run / "evidence/analysis.json", analysis)
    reference = analysis["reference"]
    write_bytes(run / "evidence/upstream-reference.py.txt", reference["quote"].encode())
    evidence = {"schema_version": 1, "repository": REPOSITORY, "parent": BUGGY, "fix": FIXED,
                "direct_parent_verified": True, "production_path": PRODUCTION, "changed_paths": changed,
                "production_diff_sha256": sha(production_diff), "analysis_sha256": sha((run / "evidence/analysis.json").read_bytes()),
                "source_files": {label: {"revision": revision, **read(run / f"snapshot-{label}.json")["files"][PRODUCTION]}
                                 for label, revision in (("A", BUGGY), ("B", FIXED))},
                "reference_evidence": {"origin": "upstream_reference", "exposure": "known before product draft",
                                       "symbol": "TLRUCacheTest.test_overwrite_existing_with_expired",
                                       "revision": FIXED, "path": "tests/test_tlru.py",
                                       "start_line": reference["start_line"], "end_line": reference["end_line"],
                                       "quote_sha256": reference["quote_sha256"]},
                "semantic_authority": "none; exact source plus separately labeled operator/upstream interpretations"}
    write(run / "evidence/evidence.json", evidence)
    evidence_hash = sha((run / "evidence/evidence.json").read_bytes())
    contract, recipe = contract_draft(evidence_hash), recipe_draft()
    validate_semantics(contract, recipe, evidence_hash)
    for folder in ("drafts", "review"):
        write(run / folder / "contract.json", contract)
        write(run / folder / "recipe.json", recipe)
    write(run / "model-proposal-status.json", {"status": "NOT_RUN", "quality": "NOT_EVALUATED",
          "reason": "Optional fresh isolated model proposal omitted; explicit operator/reference-assisted baseline",
          "operator": "Codex implementation operator", "no_autonomous_recovery_claim": True})
    immutable = ["acquisition.json", "snapshot-A.json", "snapshot-B.json", "reference-results.json",
                 "checkpoint-a.json", "evidence/evidence.json", "evidence/analysis.json", "evidence/production.diff",
                 "evidence/production-A.py", "evidence/production-B.py", "evidence/upstream-reference.py.txt",
                 "drafts/contract.json", "drafts/recipe.json", "model-proposal-status.json"]
    write(run / "review-bundle.json", {"prepared_at": now(), "immutable_files": {name: sha((run / name).read_bytes()) for name in immutable}})
    hashes = verify_review(run)
    packet = render_packet(run, evidence, analysis, contract, recipe, hashes)
    write_bytes(run / "review/REVIEW_PACKET.md", packet.encode())
    write(run / "checkpoint-b.json", {"created_at": now(), "state": "AWAITING_SEMANTIC_APPROVAL", **hashes,
                                      "review_packet_sha256": sha(packet.encode()), "approval_record_exists": False})
    return {"checkpoint": "B", "state": "AWAITING_SEMANTIC_APPROVAL", **hashes}


def status(run):
    hashes = verify_review(run)
    contract, recipe = read(run / "review/contract.json"), read(run / "review/recipe.json")
    differences = {name: corrections(read(run / "drafts" / (name + ".json")), current)
                   for name, current in (("contract", contract), ("recipe", recipe))}
    state = "AWAITING_SEMANTIC_APPROVAL"
    path = run / "semantic-decision.json"
    if path.exists():
        decision = read(path)
        state = "SEMANTICS_APPROVED" if decision["decision"] == "approve" else "REJECTED"
        if decision["hashes"] != hashes:
            state = "INVALIDATED"
        for name in ("contract", "recipe"):
            reviewed = run / "semantic-reviewed" / (name + ".json")
            if not reviewed.is_file() or sha(reviewed.read_bytes()) != decision["hashes"][name + "_sha256"]:
                state = "INVALIDATED"
    if state not in ("REJECTED", "INVALIDATED"):
        try:
            validate_semantics(contract, recipe, hashes["evidence_sha256"])
        except ValueError as exc:
            return {"state": "UNSUPPORTED_DRAFT", **hashes, "error": str(exc), "active": False}
    return {"state": state, **hashes, "developer_corrections": differences,
            "product_check_generated": False, "historical_product_validation": "NOT_RUN", "active": False}


def require_semantic_approval(run):
    state = status(run)
    if state["state"] != "SEMANTICS_APPROVED":
        raise ValueError("REAL_SEMANTIC_APPROVAL_REQUIRED: " + state["state"])
    return read(run / "semantic-decision.json")


def decide_semantics(run, *, decision, reviewer, review_minutes, note, expected_hashes, confirmed):
    if not confirmed:
        raise ValueError("An explicit developer confirmation flag is required; never auto-approve")
    validate_review_metadata(reviewer, review_minutes, note)
    actual_hashes = verify_review(run)
    if expected_hashes != actual_hashes:
        raise ValueError("REVIEW_HASH_MISMATCH: inspect current artifacts and explicitly approve their hashes")
    if decision not in ("approve", "reject"):
        raise ValueError("Unknown decision")
    contract, recipe = read(run / "review/contract.json"), read(run / "review/recipe.json")
    if decision == "approve":
        validate_semantics(contract, recipe, actual_hashes["evidence_sha256"])
    record = {"created_at": now(), "stage": "semantic_contract_and_scenario_recipe", "decision": decision,
              "reviewer": reviewer, "authorization_note": note, "review_minutes": review_minutes,
              "review_time_origin": "developer_reported_active_minutes; not inferred from elapsed time",
              "identity_assurance": "local explicit self-attestation; not strong authentication",
              "hashes": actual_hashes,
              "developer_corrections": {name: corrections(read(run / "drafts" / (name + ".json")), current)
                                        for name, current in (("contract", contract), ("recipe", recipe))}}
    # Freeze the exact reviewed bytes, including human edits, separately from editable files.
    if (run / "semantic-decision.json").exists():
        raise ValueError("Semantic decision already frozen; create a new attempt for a new decision")
    for name in ("contract", "recipe"):
        write_bytes(run / "semantic-reviewed" / (name + ".json"), (run / "review" / (name + ".json")).read_bytes())
    write(run / "semantic-decision.json", record)
    return record
