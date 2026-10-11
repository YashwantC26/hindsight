"""Trusted historical protocol. Import/preflight never executes the approved check."""
import copy
import hashlib
import math
import os
from pathlib import Path
import platform
import selectors
import signal
import subprocess
import sys
import sysconfig
import tempfile
import time

from checks import current_version, verify_check
from common import BUGGY, FIXED, HERE, REPOSITORY, now, read, sha, write, write_bytes
from execution_evidence import IncompleteExecutionError, ORDER, evaluate_history, require, verify_envelope
from review import verify_review
from semantics import validate_review_metadata
from snapshots import git, verify_acquisition

WORKER = HERE / "historical_worker.py"
ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1"}
if sys.platform == "darwin":
    # macOS inserts this at Python startup. Supply it explicitly rather than
    # inheriting the user's environment or treating it as an unknown credential.
    ENVIRONMENT["__CF_USER_TEXT_ENCODING"] = f"0x{os.getuid():X}:0x0:0x0"


def interpreter_identity():
    executable = Path(sys.executable).resolve()
    return {"executable": str(executable), "sha256": sha(executable.read_bytes()), "version": sys.version,
            "implementation": platform.python_implementation(),
            "flags": {"isolated": True, "no_site": True, "no_bytecode": True}}


def approval(record, stage):
    require(record["decision"] == "approve" and record["stage"] == stage, "MISSING_OR_REJECTED_APPROVAL")
    validate_review_metadata(record["reviewer"], record["review_minutes"], record["authorization_note"])
    require(type(record["review_minutes"]) in (int, float) and math.isfinite(record["review_minutes"]), "APPROVAL_METADATA")
    require(bool(record["created_at"]) and record["review_time_origin"] == "developer_reported_active_minutes; not inferred from elapsed time", "APPROVAL_PROVENANCE")


def verify_trust(run, check_sha256, checkpoint_sha256):
    """Independently verify approval records and pinned bytes, then reuse source gates."""
    require(current_version(run) == 2, "SUPERSEDED_OR_UNSUPPORTED_CHECK")
    require(not any(p.name != "checkpoint-c.v2.json" for p in run.glob("checkpoint-c.v*.json")), "UNSUPPORTED_NEWER_CHECKPOINT")
    require(not any(p.name != "generated-v2" for p in run.glob("generated-v*")), "SUPERSEDED_OR_PARTIAL_GENERATION")
    require(not any(p.name != "check-decision.v2.json" for p in run.glob("check-decision.v*.json")), "SUPERSEDED_CHECK_DECISION")
    b = read(run / "semantic-decision.json")
    c = read(run / "check-decision.v2.json")
    approval(b, "semantic_contract_and_scenario_recipe")
    approval(c, "exact_generated_check_and_claim_mapping")
    from datetime import datetime
    require(datetime.fromisoformat(c["created_at"]) >= datetime.fromisoformat(b["created_at"]), "APPROVAL_CHRONOLOGY")
    actual = {"check_sha256": sha((run / "generated-v2/check.py").read_bytes()),
              "checkpoint_sha256": sha((run / "checkpoint-c.v2.json").read_bytes())}
    require(actual == {"check_sha256": check_sha256, "checkpoint_sha256": checkpoint_sha256}, "PINNED_CHECK_HASH_MISMATCH")
    require(c["hashes"] == actual, "STALE_CHECK_APPROVAL")
    require(b["hashes"] == verify_review(run), "STALE_SEMANTIC_APPROVAL")
    for name in ("contract", "recipe"):
        require(sha((run / "semantic-reviewed" / (name + ".json")).read_bytes()) == b["hashes"][name + "_sha256"], "SEMANTIC_REVIEW_BYTES_MISMATCH")
    checkpoint = read(run / "checkpoint-c.v2.json")
    require(checkpoint["files"]["semantic-decision.json"] == sha((run / "semantic-decision.json").read_bytes()), "APPROVAL_CHAIN_MISMATCH")
    require(all(checkpoint[k] == v for k, v in b["hashes"].items()), "CHECKPOINT_SEMANTIC_BINDING")
    require(verify_check(run, 2) == actual, "CHECK_CONFORMANCE_OR_BINDING")
    acquisition = verify_acquisition(run)
    require(acquisition["repository"] == REPOSITORY, "REPOSITORY_MISMATCH")
    repository = Path(acquisition["local_object_source"])
    # Direct Git-object checks establish commit/tree identity beyond manifest labels.
    require(git(repository, "show", "-s", "--format=%P", FIXED).decode().strip().split() == [BUGGY], "DIRECT_PARENT_MISMATCH")
    manifests = {}
    for label, revision in (("A", BUGGY), ("B", FIXED)):
        manifest = read(run / f"snapshot-{label}.json")
        tree = {}
        for raw in git(repository, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
            if not raw:
                continue
            header, name = raw.split(b"\t", 1)
            mode, kind, oid = header.decode().split()
            require(kind == "blob" and mode in ("100644", "100755"), "UNSUPPORTED_GIT_ENTRY")
            tree[name.decode()] = (mode, oid)
        require(set(tree) == set(manifest["files"]), "GIT_TREE_FILE_SET_MISMATCH")
        for name, entry in manifest["files"].items():
            path = run / "snapshots" / label / name
            require(not Path(name).is_absolute() and ".." not in Path(name).parts and path.resolve().is_relative_to((run / "snapshots" / label).resolve()), "UNSAFE_SNAPSHOT_PATH")
            data = path.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            require((entry["git_mode"], entry["git_blob_sha1"]) == tree[name] and blob == entry["git_blob_sha1"] and len(data) == entry["size"], "GIT_BLOB_MISMATCH")
        manifests[label] = manifest
    return {**actual, **b["hashes"], "template_sha256": checkpoint["template_sha256"],
            "semantic_approval_sha256": sha((run / "semantic-decision.json").read_bytes()),
            "check_approval_sha256": sha((run / "check-decision.v2.json").read_bytes()),
            "manifest_sha256": acquisition["snapshot_manifests"], "manifests": manifests,
            "recipe": read(run / "semantic-reviewed/recipe.json"), "interpreter": interpreter_identity(),
            "worker_sha256": sha(WORKER.read_bytes()), "git_identity_verified": True}


def context_for(run, label, trust):
    return {**trust, "manifest": trust["manifests"][label], "manifest_sha256": trust["manifest_sha256"][label],
            "revision": BUGGY if label == "A" else FIXED, "snapshot_root": str((run / "snapshots" / label).resolve()),
            "worker_path": str(WORKER.resolve()), "stdlib_root": str(Path(sysconfig.get_path("stdlib")).resolve()),
            "environment": dict(ENVIRONMENT),
            "hash_file": lambda path: sha(path.read_bytes())}


class CaptureFailure(OSError):
    def __init__(self, message, captured):
        super().__init__(message)
        self.captured = captured


def capture_process(command, cwd, timeout, stdout_limit, stderr_limit):
    """All initialization after spawning is covered by bounded cleanup."""
    require(os.name == "posix", "POSIX_PROCESS_GROUPS_REQUIRED")
    require(math.isfinite(timeout) and timeout > 0 and type(stdout_limit) is int and
            type(stderr_limit) is int and stdout_limit > 0 and stderr_limit > 0, "INVALID_EXECUTION_BOUNDS")
    streams = {"stdout": bytearray(), "stderr": bytearray()}
    limits = {"stdout": stdout_limit, "stderr": stderr_limit}
    start, selector, failure = time.monotonic(), None, None
    transport = "COMPLETED"
    process = subprocess.Popen(command, cwd=cwd, env=ENVIRONMENT, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        selector = selectors.DefaultSelector()
        for name in streams:
            selector.register(getattr(process, name), selectors.EVENT_READ, name)
        while selector.get_map():
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                transport = "TIMEOUT"
                break
            for key, _ in selector.select(min(remaining, 0.05)):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                name = key.data
                space = limits[name] - len(streams[name])
                streams[name].extend(chunk[:space])
                if len(chunk) > space:
                    transport = "OUTPUT_LIMIT"
                    break
            if transport != "COMPLETED":
                break
        if transport == "COMPLETED":
            try:
                process.wait(timeout=max(0.001, timeout - (time.monotonic() - start)))
            except subprocess.TimeoutExpired:
                transport = "TIMEOUT"
    except Exception as exc:
        failure, transport = exc, "CAPTURE_ERROR"
    finally:
        # Creation, registration, collection and cleanup failures cannot bypass
        # pipe closure or reaping. Cleanup failures never become valid evidence.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            failure = failure or exc
            try:
                process.kill()
            except OSError as kill_error:
                failure = failure or kill_error
        try:
            process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired) as exc:
            failure = failure or exc
            try:
                process.kill()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired) as kill_error:
                failure = failure or kill_error
        finally:
            for pipe in (process.stdout, process.stderr):
                try:
                    pipe.close()
                except OSError as exc:
                    failure = failure or exc
            if selector is not None:
                try:
                    selector.close()
                except OSError as exc:
                    failure = failure or exc
    captured = {"transport": "CAPTURE_ERROR" if failure else transport, "pid": process.pid,
                "exit_code": process.returncode, "stdout": bytes(streams["stdout"]), "stderr": bytes(streams["stderr"]),
                "elapsed_seconds": time.monotonic() - start}
    if failure:
        raise CaptureFailure("CAPTURE_INFRASTRUCTURE_FAILURE: " + type(failure).__name__, captured) from failure
    return captured


CHECK_STDOUT_LIMIT = 32768
CHECK_STDERR_LIMIT = 8192


def invocation(run, label, destination, pins, timeout=10, stdout_limit=262144, stderr_limit=65536,
               *, launch_ledger=None, expected_trust=None):
    require(label in ("A", "B"), "UNKNOWN_SNAPSHOT")
    record = {"label": label, "started_at": now(), "evidence_valid": False, "status": "INTEGRITY_FAILURE"}
    context = None
    try:
        trust = verify_trust(run, **pins)
        require(expected_trust is None or trust == expected_trust, "PROTOCOL_TRUST_CHANGED")
        context = context_for(run, label, trust)
        invocation_id = sha(str(destination.resolve()).encode())
        request = {"invocation_id": invocation_id, "check_path": str((run / "generated-v2/check.py").resolve()),
                   "check_sha256": trust["check_sha256"], "manifest_path": str((run / f"snapshot-{label}.json").resolve()),
                   "manifest_sha256": context["manifest_sha256"], "snapshot_root": context["snapshot_root"],
                   "interpreter": trust["interpreter"], "check_stdout_limit": CHECK_STDOUT_LIMIT,
                   "check_stderr_limit": CHECK_STDERR_LIMIT}
        write(destination / "launch-request.json", request)
        request_path = destination / "launch-request.json"
        request_sha256 = sha(request_path.read_bytes())
        command = [sys.executable, "-I", "-S", "-B", str(WORKER), "--request", str(request_path),
                   "--request-sha256", request_sha256]
        context.update(invocation_id=invocation_id, request_sha256=request_sha256,
                       stdout_limit=stdout_limit, stderr_limit=stderr_limit,
                       check_stdout_limit=CHECK_STDOUT_LIMIT, check_stderr_limit=CHECK_STDERR_LIMIT)
        record.update(invocation_id=invocation_id, request_sha256=request_sha256, command=command,
                      environment=dict(ENVIRONMENT), timeout_seconds=timeout,
                      stdout_limit=stdout_limit, stderr_limit=stderr_limit, interpreter=trust["interpreter"],
                      worker_sha256=trust["worker_sha256"], approval_bindings={k: trust[k] for k in (
                          "check_sha256", "checkpoint_sha256", "semantic_approval_sha256", "check_approval_sha256")})
        with tempfile.TemporaryDirectory(prefix="hindsight-isolated-") as cwd:
            context["cwd"] = str(Path(cwd).resolve())
            record["cwd"] = context["cwd"]
            # Written before launching, independently of any returned worker object.
            write(destination / "launch-context.json", {k: v for k, v in context.items() if k != "hash_file"})
            try:
                captured = capture_process(command, cwd, timeout, stdout_limit, stderr_limit)
            except CaptureFailure as exc:
                captured = exc.captured
                record["error"] = str(exc)
        write_bytes(destination / "stdout.bin", captured["stdout"])
        write_bytes(destination / "stderr.bin", captured["stderr"])
        retained = {"label": label, "context": copy.deepcopy(context), "pid": captured["pid"],
                    "exit_code": captured["exit_code"], "transport": captured["transport"],
                    "elapsed_seconds": captured["elapsed_seconds"], "timeout_seconds": timeout,
                    "command": list(command), "worker_sha256": trust["worker_sha256"],
                    "approval_bindings": dict(record["approval_bindings"]),
                    "stdout_path": str((destination / "stdout.bin").resolve()),
                    "stderr_path": str((destination / "stderr.bin").resolve()),
                    "stdout_sha256": sha(captured["stdout"]), "stderr_sha256": sha(captured["stderr"])}
        write(destination / "collection.json", {k: v for k, v in retained.items() if k != "context"})
        if launch_ledger is not None:
            launch_ledger.append(retained)
        record.update({k: v for k, v in captured.items() if k not in ("stdout", "stderr")})
        record.update(stdout=captured["stdout"].decode("utf-8", errors="replace"), stderr=captured["stderr"].decode("utf-8", errors="replace"),
                      stdout_sha256=retained["stdout_sha256"], stderr_sha256=retained["stderr_sha256"])
        after = verify_trust(run, **pins)
        require(trust == after, "EXECUTION_INPUT_CHANGED")
        if captured["transport"] != "COMPLETED":
            record["status"] = "ERROR" if captured["transport"] == "CAPTURE_ERROR" else captured["transport"]
        else:
            require(not captured["stderr"], "UNEXPECTED_STDERR")
            from execution_evidence import decode_json, verify_raw_check, fields
            record["worker"] = decode_json(captured["stdout"])
            require(type(record["worker"]) is dict, "WORKER_RESULT_NOT_OBJECT")
            worker = record["worker"]
            # Retain raw inner streams even when their JSON is invalid. Verification
            # determines eligibility afterward; these bytes are diagnostic evidence.
            if "check_stdout_b64" in worker and "check_stderr_b64" in worker:
                raw_stdout, raw_stderr = verify_raw_check(worker, context)
                write_bytes(destination / "check-stdout.bin", raw_stdout)
                write_bytes(destination / "check-stderr.bin", raw_stderr)
            if worker.get("kind") == "hindsight_worker_error_v2":
                from execution_evidence import RAW_FIELDS
                fields(worker, {"kind", "status", "stage", "error_type", "invocation_id", "request_sha256"} | RAW_FIELDS)
                require(worker["invocation_id"] == invocation_id and worker["request_sha256"] == request_sha256,
                        "WORKER_FAILURE_INVOCATION_BINDING")
                require(captured["exit_code"] == 2 and worker["status"] == "ERROR" and type(worker["error_type"]) is str and
                        worker["stage"] in ("integrity", "check_execution", "output_limit"), "MALFORMED_WORKER_FAILURE")
                require(worker["check_output_overflow"] is False or worker["stage"] == "output_limit", "OVERFLOW_CLASSIFICATION")
                record["status"] = {"integrity": "INTEGRITY_FAILURE", "check_execution": "ERROR",
                                    "output_limit": "OUTPUT_LIMIT"}[worker["stage"]]
                record["error"] = "TRUSTED_WORKER_FAILURE"
            else:
                try:
                    verify_envelope(captured["stdout"], captured["exit_code"], context, captured["pid"])
                    record.update(status=worker["result"]["status"], evidence_valid=True)
                except IncompleteExecutionError as exc:
                    record.update(status="ERROR", error=str(exc))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError, RecursionError) as exc:
        record.update(status="INTEGRITY_FAILURE", error=str(exc), error_type=type(exc).__name__)
    record["finished_at"] = now()
    write(destination / "execution.json", record)
    return record


def historical_validation(run, pins, *, confirmed_execution=False):
    require(confirmed_execution, "EXPLICIT_HISTORICAL_EXECUTION_REQUIRED")
    trust = verify_trust(run, **pins)
    destination = run / "historical-validation-v1"
    require(not destination.exists(), "HISTORICAL_ATTEMPT_ALREADY_EXISTS")
    records, launches = [], []
    for number, label in enumerate(ORDER, 1):
        result = invocation(run, label, destination / f"invocation-{number:02}", pins,
                            launch_ledger=launches, expected_trust=trust)
        records.append({"invocation": number, "pair": (number + 1) // 2, **result})
        if result["status"] == "INTEGRITY_FAILURE":
            break
    evaluation = evaluate_history(records, launches)
    report = {"created_at": now(), "order": list(ORDER), "runs": records, "evaluation": evaluation,
              "approved_hashes": pins, "checkpoint": "D", "active": False}
    write(destination / "historical-results.json", report)
    return report
