#!/usr/bin/env python3
"""One separately authorized B/R/N demonstration. No execution on import/preflight."""
import argparse
import base64
import copy
from datetime import datetime, timezone
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from types import ModuleType

sys.dont_write_bytecode = True
ROOT = Path(__file__).absolute().parent
MVP = ROOT.parent
WORKSPACE = MVP.parent.parent
LIVE = MVP / "runs/attempt01"
BASELINE = "c0fdf6abab38040947d6fe2e38c507401d5e2350"
CHECK = "10f555bd6b96f2b23714435b9240242103d496bb70c082e1664b66a3f7bc86ec"
PINS = {
    "review_packet_sha256": "38a3f56847183da779832d64e30730a81b28d36c0eb97f351b23ec8fb4c9987b",
    "review_bindings_sha256": "cdca4f9b23c4e2eab10a0f3520cde159747ea9dfe89b633dd78a05944c3b960e",
    "approval_implementation_sha256": "f96183f31aa8d50d2b751274c0716c6d93f2cfe15981ada28d6c5eeb979bb1f6",
}
LIMITATIONS = ["INTENTIONALLY_SEEDED_REGRESSION",
               "The regression is deliberately seeded for demonstration and is not evidence of autonomous discovery of a naturally occurring AI-generated bug.",
               "Known case with upstream-test overlap; no unseen-bug discovery or generalization",
               "Locally trusted developer-inspected candidates; no hostile-code or network isolation",
               "Local self-attestation and ledgers; no strong identity or remote execution attestation"]


def response(value):
    """Attach mandatory disclosure and trust limits independently of outcome."""
    return {**value, "limitations": list(LIMITATIONS)}


def emit(value):
    print(json.dumps(response(value), indent=2, sort_keys=True, allow_nan=False))


class ResponseParser(argparse.ArgumentParser):
    def error(self, message):
        emit({"state": "BLOCKED", "regression_detected": False,
              "error_type": "ArgumentError", "reason": message})
        super().error(message)  # Preserve argparse's stderr diagnostics and exit 2.


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def same(a, b):
    return canonical(a) == canonical(b)


def safe(path, *, kind="file", missing=False):
    path = Path(path)
    require(path.is_absolute() and path.is_relative_to(WORKSPACE) and path == path.resolve(), "UNSAFE_PATH")
    require(not any(p.is_symlink() for p in (path, *path.parents)), "SYMLINK_PATH")
    if not missing:
        require(path.is_dir() if kind == "directory" else path.is_file(), "MISSING_" + kind.upper())
    return path


def raw(path):
    return safe(path).read_bytes()


def load_activation():
    path = MVP / "activation_cli.py"
    source = raw(path)
    require(sha(source) == PINS["approval_implementation_sha256"], "UNREVIEWED_ACTIVATION_IMPLEMENTATION")
    module = ModuleType("checkpoint_d_verified_source")
    module.__file__ = str(path)
    exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)
    return module


try:
    activation = load_activation()
    import historical_runner as historical
    from execution_evidence import decode_json, verify_envelope, verify_raw_check
except Exception as exc:
    if __name__ == "__main__":
        emit({"state": "BLOCKED", "regression_detected": False,
              "error_type": type(exc).__name__, "reason": str(exc)})
    raise  # Preserve bootstrap failure semantics, including the nonzero exit.

PLAN = {"order": ["B", "R", "N", "N", "R", "B", "B", "R", "N"],
        "repetitions": 3, "timeout_seconds": 10, "stdout_limit": 262144,
        "stderr_limit": 65536, "check_stdout_limit": 32768, "check_stderr_limit": 8192,
        "flags": ["-I", "-S", "-B"], "environment": dict(historical.ENVIRONMENT)}
STREAMS = {"launch-request.json", "launch-context.json", "collection.json", "execution.json",
           "stdout.bin", "stderr.bin", "check-stdout.bin", "check-stderr.bin"}


def read(path):
    return decode_json(raw(path))


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    require(type(value) is str, "TIME_TYPE")
    result = datetime.fromisoformat(value)
    require(result.utcoffset() is not None, "TIMEZONE_REQUIRED")
    return result


def pin(value):
    require(type(value) is str and re.fullmatch("[0-9a-f]{64}", value), "INVALID_SHA256")
    return value


def writable(path):
    path = safe(path, missing=True)
    require(path.is_relative_to(ROOT) and path != ROOT, "WRITE_OUTSIDE_CHECKPOINT_E")
    return path


def write_raw(path, data):
    path = writable(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe(path.parent, kind="directory")
    with path.open("xb") as stream:
        stream.write(data)


def write(path, value):
    write_raw(path, json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n")


def prepared_path(value, *, absent=False):
    require(".." not in Path(value).parts, "PATH_TRAVERSAL")
    path = Path(os.path.abspath(value))
    require(path.parent == ROOT / "prepared" and re.fullmatch(r"[A-Za-z0-9_-]+", path.name), "PREPARED_LOCATION")
    safe(path, kind="directory", missing=absent)
    if absent:
        require(not os.path.lexists(path), "PREPARATION_ALREADY_EXISTS")
    return path


def activation_gate(decision_pin, runner_pin):
    require(sha(raw(ROOT / "runner.py")) == pin(runner_pin), "RUNNER_IMPLEMENTATION_CHANGED")
    decision_raw = raw(LIVE / activation.DECISION)
    require(sha(decision_raw) == pin(decision_pin), "ACTIVATION_DECISION_CHANGED")
    verified = activation.verify_review(LIVE, **PINS)
    require(activation.validate_decision(LIVE, verified)["active"] is True, "EFFECTIVE_ACTIVE_REQUIRED")
    require(verified["scope"]["baseline_revision"] == BASELINE and
            verified["trust_pins"]["check_sha256"] == CHECK, "WRONG_BASELINE_OR_CHECK")
    trust = historical.verify_trust(LIVE, CHECK, verified["trust_pins"]["checkpoint_sha256"])
    require(same({k: trust[k] for k in activation.TRUST_KEYS}, verified["trust_pins"]), "TRUST_CHANGED")
    require(raw(LIVE / activation.DECISION) == decision_raw, "ACTIVATION_CHANGED_DURING_GATE")
    return {"decision_sha256": decision_pin, "verified": verified}, trust


def apply_patch(source, patch):
    """Exact textual hunks for one fixed path; no fuzzy matching or shell execution."""
    lines = patch.decode("utf-8").splitlines(True)
    require(lines[:2] == ["--- a/src/cachetools/__init__.py\n", "+++ b/src/cachetools/__init__.py\n"], "PATCH_PATH")
    old = source.decode("utf-8").splitlines(True)
    output, cursor, index = [], 0, 2
    require(index < len(lines), "EMPTY_PATCH")
    while index < len(lines):
        match = re.fullmatch(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@\n", lines[index])
        require(match is not None, "PATCH_HUNK")
        start, old_count, new_start, new_count = map(int, match.groups())
        require(cursor <= start - 1 <= len(old), "PATCH_RANGE")
        output.extend(old[cursor:start - 1]); cursor = start - 1
        require(len(output) == new_start - 1, "PATCH_NEW_RANGE")
        index += 1; consumed = produced = 0
        while index < len(lines) and not lines[index].startswith("@@ "):
            line = lines[index]; index += 1
            require(line[:1] in (" ", "+", "-") and line.endswith("\n"), "PATCH_LINE")
            if line[0] in " -":
                require(cursor < len(old) and old[cursor] == line[1:], "PATCH_CONTEXT")
                cursor += 1; consumed += 1
            if line[0] in " +":
                output.append(line[1:]); produced += 1
        require((consumed, produced) == (old_count, new_count), "PATCH_COUNTS")
    output.extend(old[cursor:]); result = "".join(output).encode()
    expected = "".join(difflib.unified_diff(old, result.decode().splitlines(True),
                        fromfile="a/src/cachetools/__init__.py", tofile="b/src/cachetools/__init__.py", n=3)).encode()
    require(expected == patch and result != source, "NONCANONICAL_OR_EMPTY_PATCH")
    compile(result, "candidate_static_only.py", "exec", dont_inherit=True)
    return result


def construction(trust):
    definition = read(ROOT / "candidates/definitions.json")
    require(set(definition) == {"schema_version", "baseline_revision", "path", "baseline_source_sha256", "authorship", "candidates"}
            and type(definition["schema_version"]) is int and definition["schema_version"] == 1 and
            definition["baseline_revision"] == BASELINE and definition["path"] == "src/cachetools/__init__.py" and
            set(definition["candidates"]) == {"R", "N"}, "CANDIDATE_DEFINITION")
    manifest = trust["manifests"]["B"]
    require(manifest["revision"] == BASELINE, "BASELINE_REVISION")
    source = raw(LIVE / "snapshots/B/src/cachetools/__init__.py")
    require(sha(source) == definition["baseline_source_sha256"], "BASELINE_SOURCE_CHANGED")
    sources = {"B": source}; manifests = {"B": copy.deepcopy(manifest)}
    for label in ("R", "N"):
        entry = definition["candidates"][label]
        require(set(entry) == {"disclosure", "patch_file", "patch_sha256", "source_sha256", "expected", "naturally_occurring_agent_mistake"}
                and entry["patch_file"] == label + ".patch" and entry["naturally_occurring_agent_mistake"] is False and
                entry["disclosure"] == ("INTENTIONALLY_SEEDED_REGRESSION" if label == "R" else "BENIGN_CONTROL"), "CANDIDATE_FIELDS")
        patch = raw(ROOT / "candidates" / entry["patch_file"])
        require(sha(patch) == pin(entry["patch_sha256"]), "CANDIDATE_DIFF_CHANGED")
        sources[label] = apply_patch(source, patch)
        require(sha(sources[label]) == pin(entry["source_sha256"]), "CANDIDATE_SOURCE_CHANGED")
        candidate = copy.deepcopy(manifest)
        entry_file = candidate["files"][definition["path"]]
        data = sources[label]
        entry_file.update(size=len(data), sha256=sha(data),
                          git_blob_sha1=hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest())
        candidate["files_sha256"] = sha(canonical(candidate["files"]))
        candidate["revision"] = "checkpoint-e-" + label + ":" + candidate["files_sha256"]
        manifests[label] = candidate
    return definition, sources, manifests


def verify_snapshot(root, manifest, *, identities=None):
    root = safe(root, kind="directory")
    require(manifest["files_sha256"] == sha(canonical(manifest["files"])), "MANIFEST_INTEGRITY")
    actual = set()
    expected_dirs = set()
    for name in manifest["files"]:
        require(not Path(name).is_absolute() and ".." not in Path(name).parts and Path(name).as_posix() == name, "SNAPSHOT_PATH")
        expected_dirs.update(p.as_posix() for p in Path(name).parents if p.as_posix() != ".")
    for path in root.rglob("*"):
        require(not path.is_symlink(), "SNAPSHOT_SYMLINK")
        if path.is_dir():
            require(path.relative_to(root).as_posix() in expected_dirs, "EXTRA_SNAPSHOT_DIRECTORY")
        else:
            safe(path); actual.add(path.relative_to(root).as_posix())
    require(actual == set(manifest["files"]), "SNAPSHOT_FILE_SET")
    for name, entry in manifest["files"].items():
        path = root / name; data = raw(path)
        require(sha(data) == entry["sha256"] and len(data) == entry["size"], "SNAPSHOT_SOURCE")
        identity = path.stat(follow_symlinks=False)
        require((identity.st_mode & 0o777) == (0o755 if entry["git_mode"] == "100755" else 0o644), "SNAPSHOT_MODE")
        if identities is not None:
            key = (identity.st_dev, identity.st_ino)
            require(key not in identities or identities[key] == root, "SHARED_SNAPSHOT_FILE_IDENTITY")
            identities[key] = root


def expected_bundle(prepared, decision_pin, runner_pin):
    active, trust = activation_gate(decision_pin, runner_pin)
    definition, sources, manifests = construction(trust)
    inputs = {name: sha(raw(ROOT / name)) for name in ("DESIGN.md", "evidence.schema.json", "candidates/definitions.json", "candidates/R.patch", "candidates/N.patch")}
    return {"schema_version": 1, "checkpoint": "E", "prepared_path": str(prepared),
            "activation": active, "runner_sha256": runner_pin, "baseline_revision": BASELINE,
            "definitions": definition, "manifests": manifests, "plan": copy.deepcopy(PLAN),
            "implementation_inputs": inputs, "limitations": list(LIMITATIONS)}, trust, sources


def prepare(prepared, decision_pin, runner_pin):
    prepared = prepared_path(prepared, absent=True)
    bundle, trust, sources = expected_bundle(prepared, decision_pin, runner_pin)
    writable(prepared).parent.mkdir(parents=True, exist_ok=True)
    safe(prepared.parent, kind="directory"); prepared.mkdir()  # Exclusive claim.
    for label, manifest in bundle["manifests"].items():
        for name, entry in manifest["files"].items():
            data = sources[label] if name == "src/cachetools/__init__.py" else raw(LIVE / "snapshots/B" / name)
            path = prepared / "snapshots" / label / name
            write_raw(path, data); path.chmod(0o755 if entry["git_mode"] == "100755" else 0o644)
        write(prepared / ("manifest-" + label + ".json"), manifest)
        verify_snapshot(prepared / "snapshots" / label, manifest)
    current, _, _ = expected_bundle(prepared, decision_pin, runner_pin)
    require(same(current, bundle), "PREPARATION_INPUT_DRIFT")
    write(prepared / "bundle.json", bundle)
    return {"state": "IMPLEMENTED_NOT_AUTHORIZED", "bundle_sha256": sha(raw(prepared / "bundle.json")),
            "prepared_path": str(prepared), "real_execution": False}


def verify_prepared(prepared, decision_pin, runner_pin, bundle_pin):
    prepared = prepared_path(prepared)
    saved = raw(prepared / "bundle.json")
    require(sha(saved) == pin(bundle_pin), "BUNDLE_PIN_MISMATCH")
    bundle = decode_json(saved)
    expected, trust, _ = expected_bundle(prepared, decision_pin, runner_pin)
    require(same(bundle, expected), "STALE_PREPARED_BINDINGS")
    identities = {}
    for label, manifest in bundle["manifests"].items():
        require(same(read(prepared / ("manifest-" + label + ".json")), manifest), "MANIFEST_CHANGED")
        verify_snapshot(prepared / "snapshots" / label, manifest, identities=identities)
    return bundle, trust


def atomic_record(path, value, recheck):
    path = writable(path); parent = safe(path.parent, kind="directory")
    require(not os.path.lexists(path), "RECORD_ALREADY_EXISTS")
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    pending = ".pending-" + secrets.token_hex(16); created = False
    try:
        fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        created = True
        with os.fdopen(fd, "wb") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n")
            stream.flush(); os.fsync(stream.fileno())
        recheck(); safe(parent, kind="directory")
        current, opened = parent.stat(), os.fstat(directory)
        require((current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino), "DIRECTORY_CHANGED")
        os.link(pending, path.name, src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
        os.fsync(directory)
    finally:
        try:
            if created:
                os.unlink(pending, dir_fd=directory)
        finally:
            os.close(directory)


def authorize(prepared, decision_pin, runner_pin, bundle_pin, *, reviewer, review_minutes, note, confirmed):
    metadata = activation.reviewer_metadata(reviewer, review_minutes, note, confirmed)
    bundle, _ = verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
    record = {"schema_version": 1, "stage": "checkpoint_e_bounded_execution", "decision": "authorize",
              "created_at": now(), **metadata, "confirmation": True, "bindings": bundle,
              "bundle_sha256": bundle_pin, "identity_assurance": activation.IDENTITY,
              "review_time_origin": activation.REVIEW_ORIGIN, "single_execution_directory": "execution-v1"}
    def recheck():
        current, _ = verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
        require(same(current, bundle), "AUTHORIZATION_INPUT_DRIFT")
    atomic_record(prepared / "authorization.json", record, recheck)
    return {"state": "AUTHORIZED_NOT_EXECUTED", "authorization_sha256": sha(raw(prepared / "authorization.json"))}


def verify_authorization(prepared, bundle, authorization_pin):
    data = raw(prepared / "authorization.json")
    require(sha(data) == pin(authorization_pin), "AUTHORIZATION_PIN_MISMATCH")
    record = decode_json(data)
    require(type(record) is dict and set(record) == {"schema_version", "stage", "decision", "created_at", "reviewer", "review_minutes", "authorization_note", "confirmation", "bindings", "bundle_sha256", "identity_assurance", "review_time_origin", "single_execution_directory"}, "AUTHORIZATION_FIELDS")
    require(type(record["schema_version"]) is int and record["schema_version"] == 1 and
            record["stage"] == "checkpoint_e_bounded_execution" and record["decision"] == "authorize" and
            record["identity_assurance"] == activation.IDENTITY and record["review_time_origin"] == activation.REVIEW_ORIGIN and
            record["single_execution_directory"] == "execution-v1", "INVALID_EXECUTION_AUTHORIZATION")
    activation.reviewer_metadata(record["reviewer"], record["review_minutes"], record["authorization_note"], record["confirmation"])
    require(same(record["bindings"], bundle) and record["bundle_sha256"] == sha(raw(prepared / "bundle.json")), "STALE_EXECUTION_AUTHORIZATION")
    require(timestamp(read(LIVE / activation.DECISION)["created_at"]) <= timestamp(record["created_at"]) <= datetime.now(timezone.utc), "AUTHORIZATION_CHRONOLOGY")
    return record


def launch_inputs(prepared, bundle, trust, number, label, cwd, authorization_pin):
    destination = prepared / "execution-v1" / f"invocation-{number:02}"
    manifest_path = prepared / ("manifest-" + label + ".json")
    identity = sha(str(destination).encode())
    request = {"invocation_id": identity, "check_path": str(LIVE / "generated-v2/check.py"),
               "check_sha256": CHECK, "manifest_path": str(manifest_path),
               "manifest_sha256": sha(raw(manifest_path)), "snapshot_root": str(prepared / "snapshots" / label),
               "interpreter": trust["interpreter"], "check_stdout_limit": PLAN["check_stdout_limit"],
               "check_stderr_limit": PLAN["check_stderr_limit"]}
    request_bytes = json.dumps(request, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n"
    context = historical.context_for(LIVE, "B", trust)
    context.update(manifest=bundle["manifests"][label], manifest_sha256=request["manifest_sha256"],
                   revision=bundle["manifests"][label]["revision"], snapshot_root=request["snapshot_root"],
                   cwd=cwd, invocation_id=identity, request_sha256=sha(request_bytes),
                   stdout_limit=PLAN["stdout_limit"], stderr_limit=PLAN["stderr_limit"],
                   check_stdout_limit=PLAN["check_stdout_limit"], check_stderr_limit=PLAN["check_stderr_limit"],
                   execution_authorization_sha256=authorization_pin,
                   activation_decision_sha256=bundle["activation"]["decision_sha256"],
                   prepared_bundle_sha256=sha(raw(prepared / "bundle.json")))
    command = [str(WORKSPACE / ".venv/bin/python"), *PLAN["flags"], context["worker_path"],
               "--request", str(destination / "launch-request.json"), "--request-sha256", sha(request_bytes)]
    require(str(Path(command[0]).resolve()) == trust["interpreter"]["executable"], "EXECUTION_INTERPRETER_CHANGED")
    return request, request_bytes, context, command


def analyze_invocation(prepared, bundle, trust, authorization_pin, number, label):
    """Reconstruct from independently retained collector bytes, not status assertions."""
    destination = prepared / "execution-v1" / f"invocation-{number:02}"
    actual_context = read(destination / "launch-context.json")
    cwd = actual_context["cwd"]
    require(type(cwd) is str and Path(cwd).is_absolute() and Path(cwd) == Path(cwd).resolve(), "EXECUTION_CWD")
    _, request_bytes, context, command = launch_inputs(prepared, bundle, trust, number, label, cwd, authorization_pin)
    require(raw(destination / "launch-request.json") == request_bytes, "LAUNCH_REQUEST_CHANGED")
    require(same(actual_context, {k: v for k, v in context.items() if k != "hash_file"}), "LAUNCH_CONTEXT_CHANGED")
    collection = read(destination / "collection.json")
    require(type(collection) is dict and set(collection) == {"label", "command", "pid", "exit_code", "transport", "elapsed_seconds", "timeout_seconds", "started_at", "finished_at", "collector_error_type", "stdout_sha256", "stderr_sha256", "stdout_bytes", "stderr_bytes"}, "COLLECTION_FIELDS")
    require(collection["label"] == label and collection["command"] == command and
            type(collection["timeout_seconds"]) is int and collection["timeout_seconds"] == PLAN["timeout_seconds"], "COLLECTION_METADATA")
    require(collection["transport"] in {"COMPLETED", "TIMEOUT", "OUTPUT_LIMIT", "CAPTURE_ERROR"}, "COLLECTION_TRANSPORT")
    require(type(collection["elapsed_seconds"]) in (int, float) and math.isfinite(collection["elapsed_seconds"]) and
            0 <= collection["elapsed_seconds"] <= PLAN["timeout_seconds"] + 10, "COLLECTION_DURATION")
    require(timestamp(collection["started_at"]) <= timestamp(collection["finished_at"]) <= datetime.now(timezone.utc), "COLLECTION_CHRONOLOGY")
    require((type(collection["pid"]) is int and collection["pid"] > 0) or
            (collection["pid"] is None and collection["transport"] == "CAPTURE_ERROR"), "COLLECTION_PID")
    require(type(collection["exit_code"]) is int or (collection["exit_code"] is None and collection["transport"] == "CAPTURE_ERROR"), "COLLECTION_EXIT_CODE")
    require(collection["collector_error_type"] is None or type(collection["collector_error_type"]) is str, "COLLECTION_ERROR_TYPE")
    require(collection["collector_error_type"] is None if collection["transport"] != "CAPTURE_ERROR" else bool(collection["collector_error_type"]), "COLLECTOR_ERROR_BINDING")
    streams = {}
    for name in ("stdout", "stderr"):
        data = raw(destination / (name + ".bin")); streams[name] = data
        require(type(collection[name + "_bytes"]) is int and len(data) == collection[name + "_bytes"] <= PLAN[name + "_limit"] and
                sha(data) == collection[name + "_sha256"], "COLLECTOR_STREAM_BINDING")
    # These inner bytes are retained even on an invalid envelope. Decode exactly
    # what the outer stream says when possible; otherwise require empty sentinels.
    inner = (b"", b"")
    try:
        envelope = decode_json(streams["stdout"])
        inner = verify_raw_check(envelope, context)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        pass
    for name, data in zip(("stdout", "stderr"), inner):
        require(raw(destination / ("check-" + name + ".bin")) == data, "INNER_STREAM_BINDING")
    if collection["transport"] != "COMPLETED":
        return {"status": "ERROR", "result": None, "reason": collection["transport"]}, collection
    try:
        require(collection["elapsed_seconds"] <= PLAN["timeout_seconds"] and not streams["stderr"], "COMPLETED_PROCESS_BOUNDS")
        # Full helper validation includes setup/equality classifications, twelve
        # assertions, imports, stdlib origins, identity, inner raw JSON and codes.
        context["hash_file"] = lambda path: sha(Path(path).read_bytes())
        envelope = verify_envelope(streams["stdout"], collection["exit_code"], context, collection["pid"])
        result = envelope["result"]
        require(all(s["status"] != "ERROR" for s in result["scenarios"]), "SCENARIO_ERROR")
        return {"status": result["status"], "result": result, "reason": None}, collection
    except (ValueError, OSError, TypeError, KeyError, AttributeError, RecursionError) as exc:
        return {"status": "ERROR", "result": None, "reason": "INELIGIBLE_EXECUTION: " + str(exc)}, collection


def collect_invocation(prepared, bundle, trust, authorization_pin, number, label):
    destination = prepared / "execution-v1" / f"invocation-{number:02}"
    writable(destination).mkdir()
    started = now(); error_type = None
    with tempfile.TemporaryDirectory(prefix="hindsight-e-") as cwd:
        _, request_bytes, context, command = launch_inputs(prepared, bundle, trust, number, label, str(Path(cwd).resolve()), authorization_pin)
        write_raw(destination / "launch-request.json", request_bytes)
        write(destination / "launch-context.json", {k: v for k, v in context.items() if k != "hash_file"})
        try:
            captured = historical.capture_process(command, cwd, PLAN["timeout_seconds"], PLAN["stdout_limit"], PLAN["stderr_limit"])
        except historical.CaptureFailure as exc:
            captured = exc.captured; error_type = type(exc).__name__
        except (OSError, subprocess.SubprocessError) as exc:
            captured = {"transport": "CAPTURE_ERROR", "pid": None, "exit_code": None,
                        "stdout": b"", "stderr": b"", "elapsed_seconds": 0.0}
            error_type = type(exc).__name__
    finished = now()
    collection = {"label": label, "command": command, "timeout_seconds": PLAN["timeout_seconds"],
                  "started_at": started, "finished_at": finished, "collector_error_type": error_type,
                  **{k: captured[k] for k in ("transport", "pid", "exit_code", "elapsed_seconds")}}
    for name in ("stdout", "stderr"):
        data = captured[name]; write_raw(destination / (name + ".bin"), data)
        collection[name + "_sha256"] = sha(data); collection[name + "_bytes"] = len(data)
    write(destination / "collection.json", collection)
    inner = (b"", b"")
    try:
        inner = verify_raw_check(decode_json(captured["stdout"]), context)
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        pass
    for name, data in zip(("stdout", "stderr"), inner):
        write_raw(destination / ("check-" + name + ".bin"), data)
    result, _ = analyze_invocation(prepared, bundle, trust, authorization_pin, number, label)
    write(destination / "execution.json", {"invocation": number, "label": label,
          "repetition": PLAN["order"][:number].count(label), **result})
    return result


def classification(records):
    """Only complete independently validated results can count as claim violations."""
    outcomes = {}
    if len(records) != 9:
        return {"status": "INCONCLUSIVE", "candidates": {}, "demo_expectations_met": False,
                "explanation": "Nine complete invocations are required."}
    groups = {label: [r for actual, r in records if actual == label] for label in ("B", "R", "N")}
    if any(len(values) != 3 for values in groups.values()):
        return {"status": "INCONCLUSIVE", "candidates": {}, "demo_expectations_met": False,
                "explanation": "Exactly three repetitions per identity are required."}
    def group_status(values):
        if any(v["status"] == "ERROR" for v in values):
            return "ERROR"
        if not all(same(v["result"], values[0]["result"]) for v in values):
            return "UNSTABLE"
        return values[0]["status"]
    baseline = group_status(groups["B"])
    for label in ("R", "N"):
        status = group_status(groups[label])
        failures = []
        if status in ("PASS", "FAIL"):
            for scenario in groups[label][0]["result"]["scenarios"]:
                failures.extend({"scenario_id": scenario["scenario_id"], "claim_id": a["claim_id"],
                                 "assertion_id": a["assertion_id"], "observed": a["observed"], "expected": a["expected"]}
                                for a in scenario["assertions"] if a["status"] == "FAIL")
        effective = "ERROR" if baseline == "ERROR" or status == "ERROR" else (
            "UNSTABLE" if baseline == "UNSTABLE" or status == "UNSTABLE" else (
            "INCONCLUSIVE" if baseline != "PASS" else ("REGRESSION_DETECTED" if status == "FAIL" and failures else status)))
        outcomes[label] = {"status": effective, "violations": failures,
                           "explanation": "Stable approved-claim violation against passing baseline." if effective == "REGRESSION_DETECTED" else
                               "All scoped assertions pass in three repetitions." if effective == "PASS" else
                               "Execution is ineligible, inconsistent, or the baseline is not passing."}
    expected = {(s, c) for s in ("expiry_at_boundary", "expiry_before_boundary") for c in ("C1", "C2")}
    got = {(v["scenario_id"], v["claim_id"]) for v in outcomes["R"]["violations"]}
    met = baseline == "PASS" and outcomes["R"]["status"] == "REGRESSION_DETECTED" and got == expected and outcomes["N"]["status"] == "PASS"
    statuses = {v["status"] for v in outcomes.values()}
    overall = next((s for s in ("ERROR", "UNSTABLE", "INCONCLUSIVE", "REGRESSION_DETECTED", "PASS") if s in statuses), "INCONCLUSIVE")
    return {"status": overall, "baseline": baseline, "candidates": outcomes, "demo_expectations_met": met,
            "explanation": "Computed from retained evidence; seeded condition disclosed, finite scope only."}


def evidence_inventory(root, *, allow_pending=False):
    root = safe(root, kind="directory"); entries = {}
    expected_dirs = {f"invocation-{n:02}" for n in range(1, 10)}
    for path in root.rglob("*"):
        require(not path.is_symlink(), "EVIDENCE_SYMLINK")
        name = path.relative_to(root).as_posix()
        if path.is_dir():
            require(name in expected_dirs, "EXTRA_EVIDENCE_DIRECTORY")
        elif allow_pending and re.fullmatch(r"\.pending-[0-9a-f]{32}", name):
            safe(path)
        elif name != "report.json":
            data = raw(path); entries[name] = {"sha256": sha(data), "size": len(data)}
    expected = {f"invocation-{n:02}/{name}" for n in range(1, 10) for name in STREAMS}
    require(set(entries) == expected, "PARTIAL_OR_EXTRA_EVIDENCE")
    return entries


def reconstruct(prepared, bundle, trust, authorization_pin, authorization):
    records = []; seen_pid = set(); seen_cwd = set()
    previous = timestamp(authorization["created_at"])
    for number, label in enumerate(PLAN["order"], 1):
        result, col = analyze_invocation(prepared, bundle, trust, authorization_pin, number, label)
        require(previous <= timestamp(col["started_at"]), "INVOCATION_CHRONOLOGY")
        previous = timestamp(col["finished_at"])
        if col["pid"] is not None:
            require(col["pid"] not in seen_pid, "DUPLICATE_PROCESS")
            seen_pid.add(col["pid"])
        cwd = read(prepared / "execution-v1" / f"invocation-{number:02}/launch-context.json")["cwd"]
        require(cwd not in seen_cwd, "DUPLICATE_CWD"); seen_cwd.add(cwd)
        require(same(read(prepared / "execution-v1" / f"invocation-{number:02}/execution.json"),
                     {"invocation": number, "label": label, "repetition": PLAN["order"][:number].count(label), **result}), "EXECUTION_RECORD_DISAGREEMENT")
        records.append((label, result))
    return classification(records), previous


def execute(prepared, decision_pin, runner_pin, bundle_pin, authorization_pin, *, confirmed=False):
    require(confirmed is True, "EXPLICIT_EXECUTION_REQUIRED")
    bundle, trust = verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
    authorization = verify_authorization(prepared, bundle, authorization_pin)
    root = writable(prepared / "execution-v1"); root.mkdir()  # No overwrite or resume.
    for number, label in enumerate(PLAN["order"], 1):
        current, trust = verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
        require(same(current, bundle), "PROTOCOL_INPUT_CHANGED")
        verify_authorization(prepared, bundle, authorization_pin)
        collect_invocation(prepared, bundle, trust, authorization_pin, number, label)
        verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
        verify_authorization(prepared, bundle, authorization_pin)
    summary, _ = reconstruct(prepared, bundle, trust, authorization_pin, authorization)
    report = response({"schema_version": 1, "checkpoint": "E", "created_at": now(), "bindings": bundle,
              "authorization_sha256": authorization_pin, "classification": summary,
              "evidence_inventory": evidence_inventory(root)})
    def recheck():
        verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
        verify_authorization(prepared, bundle, authorization_pin)
        require(same(evidence_inventory(root, allow_pending=True), report["evidence_inventory"]), "EVIDENCE_CHANGED_BEFORE_PUBLICATION")
    atomic_record(root / "report.json", report, recheck)
    return verify_evidence(prepared, decision_pin, runner_pin, bundle_pin, authorization_pin)


def verify_evidence(prepared, decision_pin, runner_pin, bundle_pin, authorization_pin):
    bundle, trust = verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
    authorization = verify_authorization(prepared, bundle, authorization_pin)
    root = prepared / "execution-v1"
    if not os.path.lexists(root / "report.json"):
        return response({"status": "INCONCLUSIVE", "demo_expectations_met": False, "reason": "No complete published report; no detection claim."})
    report = read(root / "report.json")
    require(type(report) is dict and set(report) == {"schema_version", "checkpoint", "created_at", "bindings", "authorization_sha256", "classification", "evidence_inventory", "limitations"}
            and type(report["schema_version"]) is int and report["schema_version"] == 1 and report["checkpoint"] == "E", "REPORT_FIELDS")
    require(same(report["bindings"], bundle) and report["authorization_sha256"] == authorization_pin and same(report["limitations"], LIMITATIONS), "REPORT_BINDINGS")
    require(same(report["evidence_inventory"], evidence_inventory(root)), "EVIDENCE_INVENTORY_CHANGED")
    summary, finish = reconstruct(prepared, bundle, trust, authorization_pin, authorization)
    require(finish <= timestamp(report["created_at"]) <= datetime.now(timezone.utc) and same(summary, report["classification"]), "REPORT_CLASSIFICATION_OR_TIME")
    # Revalidate inputs after retained-evidence reconstruction, too.
    verify_prepared(prepared, decision_pin, runner_pin, bundle_pin)
    verify_authorization(prepared, bundle, authorization_pin)
    return response({"verification": "COMPLETED_EVIDENCE_VERIFIED", **summary})


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = ResponseParser(description=__doc__, allow_abbrev=False)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "prepare", "authorize", "execute", "verify-evidence"):
        sub = subs.add_parser(name, allow_abbrev=False)
        sub.add_argument("--runner-sha256", required=True)
        sub.add_argument("--activation-decision-sha256", required=True)
        if name != "preflight":
            sub.add_argument("--prepared-dir", required=True)
        if name in ("authorize", "execute", "verify-evidence"):
            sub.add_argument("--bundle-sha256", required=True)
        if name in ("execute", "verify-evidence"):
            sub.add_argument("--authorization-sha256", required=True)
        if name == "authorize":
            sub.add_argument("--reviewer", required=True); sub.add_argument("--review-minutes", type=float, required=True)
            sub.add_argument("--authorization-note", required=True)
            sub.add_argument("--confirm-execution-authorization", action="store_true", required=True)
        if name == "execute":
            sub.add_argument("--confirm-execute", action="store_true", required=True)
    options = [a.split("=", 1)[0] for a in argv if a.startswith("--")]
    if len(options) != len(set(options)):
        parser.error("duplicate options forbidden")
    args = parser.parse_args(argv)
    try:
        decision, implementation = args.activation_decision_sha256, args.runner_sha256
        if args.command == "preflight":
            active, trust = activation_gate(decision, implementation)
            definition, _, manifests = construction(trust)
            result = {"state": "PREFLIGHT_VERIFIED", "effective_activation": "ACTIVE",
                      "baseline": BASELINE, "candidates": definition, "plan": PLAN,
                      "source_trees": {k: v["files_sha256"] for k, v in manifests.items()}, "real_execution": False}
        else:
            prepared = prepared_path(args.prepared_dir, absent=args.command == "prepare")
            if args.command == "prepare":
                result = prepare(prepared, decision, implementation)
            elif args.command == "authorize":
                result = authorize(prepared, decision, implementation, args.bundle_sha256, reviewer=args.reviewer,
                                   review_minutes=args.review_minutes, note=args.authorization_note,
                                   confirmed=args.confirm_execution_authorization)
            elif args.command == "execute":
                result = execute(prepared, decision, implementation, args.bundle_sha256, args.authorization_sha256, confirmed=args.confirm_execute)
            else:
                result = verify_evidence(prepared, decision, implementation, args.bundle_sha256, args.authorization_sha256)
        emit(result)
        return 2 if result.get("status") in ("ERROR", "UNSTABLE", "INCONCLUSIVE") or (
            args.command == "execute" and not result.get("demo_expectations_met")) else 0
    except (ValueError, OSError, KeyError, TypeError, AttributeError, RecursionError, OverflowError, subprocess.SubprocessError) as exc:
        emit({"state": "BLOCKED", "regression_detected": False, "error_type": type(exc).__name__, "reason": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
