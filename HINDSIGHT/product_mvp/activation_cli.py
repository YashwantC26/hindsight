#!/usr/bin/env python3
"""Standalone Checkpoint D approval. Never executes historical or candidate code.

Version 1 supports only the immutable attempt01 activation-review-v1 package.
verify-review reads evidence; approve-activation requires a separate human decision.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import sys
from types import ModuleType

# Importing this standalone mechanism must not produce bytecode artifacts.
sys.dont_write_bytecode = True
# Check all helper bytes before importing any repository code. Load the verified
# buffers directly so cached bytecode or PYTHONPATH cannot replace those helpers.
DEPENDENCY_HASHES = {
    "common": "c62ae79240f971595dd332160330dd9214588bba2467e8281622183c27da4a20",
    "snapshots": "7bb1ce603b50894de648bfca8cdf3eedf0d19f50aba555e4df81c1122ef40f2d",
    "navigation": "f1af57ca17edf9fd5e5096ca0574a5ed5404eb255a94be8473267dce7d96ed5f",
    "semantics": "b1ddd83f51f56eae5474779196d2deb33567f9ed6acc72cecb35eef1a59dbf8a",
    "review": "1638eb0a11a362dee75cea2dccd9991595ec20a5acb1e04d6eab9eaeff358ec9",
    "checks": "053aba8d9b7715212765a779bc2ff74fa134f906cdc1ef1919ea5a88a481a00a",
    "execution_evidence": "d819de6b03286e4e3cab0a2dea62e92ab470a4018e4e51a58905c736f26f15c0",
    "historical_runner": "6494cc12b331c343a87c5014954a3b943f38cf0a1f815fd362008b7392c27799",
}


def dependency_buffers(here):
    buffers = {}
    for name, expected in DEPENDENCY_HASHES.items():
        path = here / (name + ".py")
        if path != path.resolve() or any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError("UNSAFE_DEPENDENCY_PATH: " + name)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("DEPENDENCY_CHANGED: " + name)
        buffers[name] = (path, raw)
    return buffers


def bootstrap_dependencies():
    buffers = dependency_buffers(Path(__file__).absolute().parent)
    for name, (path, raw) in buffers.items():
        if name in sys.modules:
            if getattr(sys.modules[name], "__file__", None) != str(path):
                raise ValueError("PRELOADED_DEPENDENCY_ORIGIN: " + name)
        else:
            module = ModuleType(name)
            module.__file__, module.__package__, module.__cached__ = str(path), "", None
            sys.modules[name] = module
            try:
                exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)
            except BaseException:
                del sys.modules[name]
                raise


try:
    bootstrap_dependencies()
except (ValueError, OSError) as bootstrap_error:
    if __name__ == "__main__":
        print(json.dumps({"status": "BLOCKED", "active": False, "reason": str(bootstrap_error)}))
        raise SystemExit(2)
    raise

from common import FIXED, HERE, WORKSPACE
from execution_evidence import decode_json, evaluate_history, require, same_json
from historical_runner import context_for, verify_trust
from semantics import validate_review_metadata

REVIEW = "activation-review-v1"
DECISION = "activation-decision.v1.json"
STAGE = "historically_validated_check_activation"
IDENTITY = "local explicit self-attestation; not strong authentication"
REVIEW_ORIGIN = "developer_reported_active_minutes; not inferred from elapsed time"
# An edited/re-pinned manifest is not a new supported review. New reviews need a
# separately reviewed implementation/version rather than an editable trust oracle.
ANCHORS = {
    "activation-review-v1/REVIEW_PACKET.md": "38a3f56847183da779832d64e30730a81b28d36c0eb97f351b23ec8fb4c9987b",
    "activation-review-v1/review-bindings.json": "cdca4f9b23c4e2eab10a0f3520cde159747ea9dfe89b633dd78a05944c3b960e",
    "activation-review-v1/ACTIVATION_PROCEDURE.md": "d05a2d4a1d65bf7b9e8507e91d7c2888e62ff533bf835b1a8bce1d146b9e6b08",
    "CURRENT_STATUS.v1.md": "a902077fa4c1a557a5043a9f1bc4bc97f1215429fe820f1ee666691138292a36",
}
STREAM_FILES = {"launch-request.json", "launch-context.json", "collection.json",
                "execution.json", "stdout.bin", "stderr.bin", "check-stdout.bin", "check-stderr.bin"}
TRUST_KEYS = ("bundle_sha256", "check_approval_sha256", "check_sha256", "checkpoint_sha256",
              "contract_sha256", "evidence_sha256", "interpreter", "manifest_sha256",
              "recipe_sha256", "semantic_approval_sha256", "template_sha256", "worker_sha256")
SCOPE = {"contract_id": "cachetools-tlru-expired-replacement", "contract_version": 1,
         "check_generation_version": 2, "template_id": "tlru_expired_replacement_v1",
         "baseline_revision": FIXED,
         "scenario_ids": ["expiry_at_boundary", "expiry_before_boundary", "valid_replacement", "absent_target"],
         "application": "bounded separately authorized future-patch demo",
         "future_execution_authorized": False}
ORDER = ("A", "B", "B", "A", "A", "B")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def hash_pin(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None, "INVALID_HASH_PIN")
    return value


def safe_path(path, *, directory=False):
    """Canonical paths and every ancestor below the workspace must be unlinked."""
    path = Path(path)
    require(path.is_absolute() and path.is_relative_to(WORKSPACE) and path == path.resolve(), "UNSAFE_PATH")
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), "SYMLINK_PATH")
        if parent == WORKSPACE:
            break
    require(path.is_dir() if directory else path.is_file(), "MISSING_DIRECTORY" if directory else "MISSING_FILE")
    return path


def read_bytes(path):
    return safe_path(path).read_bytes()


def read_json(path):
    return decode_json(read_bytes(path))


def run_path(value):
    path = Path(os.path.abspath(value))
    require(".." not in Path(value).parts, "RUN_PATH_TRAVERSAL")
    require(path == HERE / "runs/attempt01", "UNSUPPORTED_RUN_OR_REVIEW_VERSION")
    return safe_path(path, directory=True)


def input_path(name):
    require(type(name) is str, "INPUT_PATH_TYPE")
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and relative.as_posix() == name and
            not {"..", "."}.intersection(relative.parts) and name.startswith("HINDSIGHT/"), "INPUT_PATH_ESCAPE")
    return safe_path(WORKSPACE / name)


def historical_file_set(run):
    root = safe_path(run / "historical-validation-v1", directory=True)
    expected = {"historical-results.json"} | {
        f"invocation-{n:02}/{name}" for n in range(1, 7) for name in STREAM_FILES}
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "HISTORICAL_SYMLINK")
        if path.is_dir():
            require(path.parent == root and path.name in {f"invocation-{n:02}" for n in range(1, 7)},
                    "EXTRA_HISTORICAL_DIRECTORY")
        else:
            safe_path(path)
            actual.add(path.relative_to(root).as_posix())
    require(actual == expected, "HISTORICAL_FILE_SET")
    return {str((root / name).relative_to(WORKSPACE)) for name in expected}


def verify_history(run, bindings, trust):
    """Reconstruct collector records, never call invocation/historical_validation."""
    root = run / "historical-validation-v1"
    report = read_json(root / "historical-results.json")
    require(report["checkpoint"] == "D" and report["active"] is False and report["order"] == list(ORDER)
            and type(report["runs"]) is list and len(report["runs"]) == 6, "HISTORICAL_REPORT_PROTOCOL")
    require(same_json(report["approved_hashes"], {k: trust[k] for k in ("check_sha256", "checkpoint_sha256")}),
            "HISTORICAL_APPROVAL_PINS")
    records, launches, results = [], [], {"A": [], "B": []}
    seen = {"pid": set(), "cwd": set(), "id": set()}
    previous_finish = datetime.fromisoformat(read_json(run / "check-decision.v2.json")["created_at"])
    totals = {"PASS": 0, "FAIL": 0}
    for number, label in enumerate(ORDER, 1):
        dest = root / f"invocation-{number:02}"
        context = read_json(dest / "launch-context.json")
        current = context_for(run, label, trust)
        for key, value in current.items():
            if key != "hash_file":
                require(same_json(context[key], value), "STALE_LAUNCH_CONTEXT: " + key)
        require(context["stdout_limit"] == 262144 and context["stderr_limit"] == 65536 and
                context["check_stdout_limit"] == 32768 and context["check_stderr_limit"] == 8192, "EXECUTION_BOUNDS")
        request_raw = read_bytes(dest / "launch-request.json")
        request = decode_json(request_raw)
        request_hash = sha(request_raw)
        identity = sha(str(dest).encode())
        expected = {"invocation_id": identity, "check_path": str(run / "generated-v2/check.py"),
                    "check_sha256": trust["check_sha256"], "manifest_path": str(run / f"snapshot-{label}.json"),
                    "manifest_sha256": current["manifest_sha256"], "snapshot_root": current["snapshot_root"],
                    "interpreter": trust["interpreter"], "check_stdout_limit": 32768, "check_stderr_limit": 8192}
        require(same_json(request, expected) and context["invocation_id"] == identity and
                context["request_sha256"] == request_hash, "LAUNCH_REQUEST_BINDING")
        record = read_json(dest / "execution.json")
        collection = read_json(dest / "collection.json")
        numbered = {"invocation": number, "pair": (number + 1) // 2, **record}
        require("invocation" not in record and "pair" not in record and
                same_json(report["runs"][number - 1], numbered), "REPORT_EXECUTION_DISAGREEMENT")
        command = [str(WORKSPACE / ".venv/bin/python"), "-I", "-S", "-B", current["worker_path"],
                   "--request", str(dest / "launch-request.json"), "--request-sha256", request_hash]
        require(record["command"] == command and collection["command"] == command and
                str(Path(command[0]).resolve()) == trust["interpreter"]["executable"], "LAUNCH_COMMAND")
        approval = {k: trust[k] for k in ("check_sha256", "checkpoint_sha256", "semantic_approval_sha256", "check_approval_sha256")}
        require(same_json(collection["approval_bindings"], approval) and
                same_json(record["approval_bindings"], approval), "COLLECTOR_APPROVAL_BINDINGS")
        for key in ("pid", "cwd"):
            require(record[key] not in seen[key], "REUSED_LAUNCH_METADATA")
            seen[key].add(record[key])
        require(identity not in seen["id"], "REUSED_INVOCATION")
        seen["id"].add(identity)
        start, finish = (datetime.fromisoformat(record[k]) for k in ("started_at", "finished_at"))
        require(previous_finish <= start <= finish and start.utcoffset() is not None, "EXECUTION_CHRONOLOGY")
        previous_finish = finish
        require(record["timeout_seconds"] == 10 and "error" not in record and "error_type" not in record, "EXECUTION_FAILURE")
        for name in ("stdout", "stderr"):
            require(collection[name + "_path"] == str(dest / (name + ".bin")), "COLLECTOR_STREAM_PATH")
        worker = decode_json(read_bytes(dest / "stdout.bin"))
        for name in ("stdout", "stderr"):
            raw = read_bytes(dest / ("check-" + name + ".bin"))
            require(raw == base64.b64decode(worker["check_" + name + "_b64"], validate=True) and
                    sha(raw) == worker["check_" + name + "_sha256"], "RETAINED_INNER_STREAM")
        # The existing verifier checks all twelve assertions, setups, origins,
        # types, envelopes, exit codes, transport and outer raw stream bindings.
        launches.append({**collection, "context": {**context, "hash_file": lambda p: sha(read_bytes_external(p))}})
        records.append(numbered)
        result = worker["result"]
        results[label].append(result)
        for scenario in result["scenarios"]:
            for assertion in scenario["assertions"]:
                wanted = "FAIL" if label == "A" and scenario["historical_role"] == "discriminator" and assertion["claim_id"] in ("C1", "C2") else "PASS"
                require(assertion["status"] == wanted, "DESIGNATED_ASSERTION_PATTERN")
                totals[wanted] += 1
    require(datetime.fromisoformat(report["created_at"]) >= previous_finish, "REPORT_CHRONOLOGY")
    evaluation = evaluate_history(records, launches)
    require(evaluation["accepted"] is True and evaluation["stable"] is True and evaluation["reasons"] == []
            and evaluation["active"] is False and same_json(evaluation, report["evaluation"]), "HISTORICAL_ACCEPTANCE_REJECTED")
    require(same_json(evaluation, bindings["historical_evaluation_recomputed"]) and
            bindings["historical_order"] == list(ORDER) and same_json(totals, bindings["assertion_totals"]), "REVIEW_ACCEPTANCE_BINDING")
    for label in ("A", "B"):
        require(len(results[label]) == 3 and all(same_json(r, results[label][0]) for r in results[label]), "REPEATED_RESULT_DISAGREEMENT")
        require(same_json(results[label][0]["scenarios"], bindings["assertion_comparison"][label]), "REVIEW_ASSERTION_BINDING")
    return evaluation


def read_bytes_external(path):
    """Stdlib origins live outside workspace; evaluator restricts their roots."""
    path = Path(path)
    require(path.is_absolute() and path == path.resolve() and path.is_file() and not path.is_symlink(), "MODULE_PATH")
    return path.read_bytes()


def verify_review(run, review_packet_sha256, review_bindings_sha256, approval_implementation_sha256):
    run = run_path(run)
    supplied = {"review_packet_sha256": hash_pin(review_packet_sha256),
                "review_bindings_sha256": hash_pin(review_bindings_sha256),
                "approval_implementation_sha256": hash_pin(approval_implementation_sha256)}
    require(supplied["review_packet_sha256"] == ANCHORS[REVIEW + "/REVIEW_PACKET.md"] and
            supplied["review_bindings_sha256"] == ANCHORS[REVIEW + "/review-bindings.json"], "UNSUPPORTED_REVIEW_PINS")
    material = {name: sha(read_bytes(run / name)) for name in ANCHORS}
    require(material == ANCHORS, "REVIEW_MATERIAL_CHANGED")
    require(sha(read_bytes(HERE / "activation_cli.py")) == supplied["approval_implementation_sha256"], "APPROVAL_IMPLEMENTATION_CHANGED")
    bindings = read_json(run / REVIEW / "review-bindings.json")
    require(type(bindings["schema_version"]) is int and bindings["schema_version"] == 1 and
            bindings["workspace_root"] == str(WORKSPACE) and bindings["checkpoint"] == "D" and bindings["active"] is False,
            "REVIEW_VERSION_OR_ROOT")
    inputs = bindings["bound_inputs"]
    require(type(inputs) is dict and len(inputs) == 203 and type(bindings["bound_input_count"]) is int and
            bindings["bound_input_count"] == 203 and bindings["verification_errors"] == [], "REVIEW_INPUT_INVENTORY")
    for name, entry in inputs.items():
        require(type(entry) is dict and set(entry) == {"sha256", "size"} and type(entry["size"]) is int and
                entry["size"] >= 0, "INPUT_BINDING_FIELDS")
        raw = read_bytes(input_path(name))
        require(len(raw) == entry["size"] and sha(raw) == hash_pin(entry["sha256"]), "BOUND_INPUT_CHANGED: " + name)
    historical = historical_file_set(run)
    prefix = str((run / "historical-validation-v1").relative_to(WORKSPACE)) + "/"
    require({name for name in inputs if name.startswith(prefix)} == historical, "HISTORICAL_BINDING_FILE_SET")
    # Strictly parse every JSON input, even ones only hashed by legacy gates.
    for name in inputs:
        if name.endswith(".json"):
            read_json(input_path(name))
    pins = bindings["trust_pins"]
    require(set(pins) == set(TRUST_KEYS), "TRUST_PIN_FIELDS")
    trust = verify_trust(run, pins["check_sha256"], pins["checkpoint_sha256"])
    require(same_json(pins, {k: trust[k] for k in TRUST_KEYS}), "CURRENT_TRUST_DISAGREEMENT")
    report_hash = sha(read_bytes(run / "historical-validation-v1/historical-results.json"))
    require(report_hash == bindings["historical_report_sha256"], "HISTORICAL_REPORT_BINDING")
    evaluation = verify_history(run, bindings, trust)
    return {"review_pins": supplied, "review_materials": material, "input_bindings": inputs,
            "trust_pins": pins, "historical_report_sha256": report_hash, "historical_evaluation": evaluation,
            "scope": dict(SCOPE)}


def reviewer_metadata(reviewer, review_minutes, authorization_note, confirmed):
    require(confirmed is True, "EXPLICIT_DEVELOPER_CONFIRMATION_REQUIRED")
    require(type(reviewer) is str and type(authorization_note) is str and
            type(review_minutes) in (int, float) and math.isfinite(review_minutes) and review_minutes > 0,
            "INVALID_REVIEW_METADATA")
    validate_review_metadata(reviewer, review_minutes, authorization_note)
    return {"reviewer": reviewer, "review_minutes": review_minutes, "authorization_note": authorization_note}


def validate_decision(run, verified):
    """Eligibility derives from an exact complete approval, never file presence."""
    path = run / DECISION
    if not os.path.lexists(path):
        return {"state": "IMPLEMENTED_NOT_APPROVED", "active": False}
    record = read_json(path)
    required = {"schema_version", "stage", "decision", "created_at", "reviewer", "review_minutes", "authorization_note",
                "confirmation", "review_time_origin", "identity_assurance", "active", "bindings"}
    require(type(record) is dict and set(record) == required and type(record["schema_version"]) is int and
            record["schema_version"] == 1 and record["stage"] == STAGE and record["decision"] == "approve" and
            record["active"] is True and record["review_time_origin"] == REVIEW_ORIGIN and record["identity_assurance"] == IDENTITY,
            "INVALID_ACTIVATION_DECISION")
    reviewer_metadata(record["reviewer"], record["review_minutes"], record["authorization_note"], record["confirmation"])
    created = datetime.fromisoformat(record["created_at"])
    require(created.utcoffset() is not None and datetime.fromisoformat(read_json(run / "historical-validation-v1/historical-results.json")["created_at"]) <= created <= datetime.now(timezone.utc), "ACTIVATION_CHRONOLOGY")
    require(same_json(record["bindings"], verified), "STALE_ACTIVATION_DECISION")
    return {"state": "ACTIVE", "active": True, "decision_path": str(path)}


def publish_exclusive(run, raw, recheck):
    """POSIX hard-link publication: a complete fsynced file, atomic no-overwrite.

    The open directory descriptor keeps both temporary/final names in one trusted
    directory. Directory identity and evidence are rechecked just before linking.
    A crash after publication can leave a complete decision; never overwrite it.
    """
    run = run_path(run)
    require(os.name == "posix" and not os.path.lexists(run / DECISION), "ACTIVATION_DECISION_ALREADY_EXISTS_OR_UNSUPPORTED_PLATFORM")
    directory = os.open(run, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = ".activation-pending-" + secrets.token_hex(16)
    created = False
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        recheck()
        safe_path(run, directory=True)
        current, opened = run.stat(), os.fstat(directory)
        require((current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino), "DECISION_DIRECTORY_CHANGED")
        os.link(temporary, DECISION, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        os.fsync(directory)
    finally:
        try:
            if created:
                os.unlink(temporary, dir_fd=directory)
        finally:
            os.close(directory)


def approve_activation(run, *, reviewer, review_minutes, authorization_note, confirmed, **pins):
    metadata = reviewer_metadata(reviewer, review_minutes, authorization_note, confirmed)
    run = run_path(run)
    require(not os.path.lexists(run / DECISION), "ACTIVATION_DECISION_ALREADY_EXISTS")
    verified = verify_review(run, **pins)
    record = {"schema_version": 1, "stage": STAGE, "decision": "approve", "created_at": datetime.now(timezone.utc).isoformat(),
              **metadata, "confirmation": True, "review_time_origin": REVIEW_ORIGIN, "identity_assurance": IDENTITY,
              "active": True, "bindings": verified}
    raw = (json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    def recheck():
        require(same_json(verify_review(run, **pins), verified), "APPROVAL_INPUT_CHANGED")
    publish_exclusive(run, raw, recheck)
    # A post-publication drift leaves an invalid historical decision, never a
    # false successful activation or an overwritten/erased approval record.
    return validate_decision(run, verify_review(run, **pins))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subcommands = parser.add_subparsers(dest="command", required=True)
    for name in ("verify-review", "approve-activation"):
        sub = subcommands.add_parser(name, allow_abbrev=False)
        sub.add_argument("--run-dir", required=True)
        for field in ("review-packet", "review-bindings", "approval-implementation"):
            sub.add_argument("--" + field + "-sha256", required=True)
        if name == "approve-activation":
            sub.add_argument("--reviewer", required=True)
            sub.add_argument("--review-minutes", type=float, required=True)
            sub.add_argument("--authorization-note", required=True)
            sub.add_argument("--confirm-developer-decision", action="store_true", required=True)
    options = [token.split("=", 1)[0] for token in argv if token.startswith("--")]
    if len(options) != len(set(options)):
        parser.error("duplicate options are not permitted")
    args = parser.parse_args(argv)
    run = None
    try:
        run = run_path(args.run_dir)
        pins = {k: getattr(args, k) for k in ("review_packet_sha256", "review_bindings_sha256", "approval_implementation_sha256")}
        if args.command == "verify-review":
            verified = verify_review(run, **pins)
            result = {"status": "REVIEW_VERIFIED", "historical_evaluation": verified["historical_evaluation"],
                      "bound_input_count": len(verified["input_bindings"]), **validate_decision(run, verified)}
        else:
            result = {"status": "DECISION_RECORDED", **approve_activation(run, reviewer=args.reviewer,
                      review_minutes=args.review_minutes, authorization_note=args.authorization_note,
                      confirmed=args.confirm_developer_decision, **pins)}
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        invalidated = args.command == "verify-review" and run is not None and os.path.lexists(run / DECISION)
        print(json.dumps({"status": "INVALIDATED" if invalidated else "BLOCKED", "active": False,
                          "error_type": type(exc).__name__, "reason": str(exc)}, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
