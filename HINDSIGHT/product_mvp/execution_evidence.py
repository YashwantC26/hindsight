"""Independent finite execution-evidence validator; no cache imports or execution."""
import _imp
import base64
import hashlib
import json
import math
from pathlib import Path

from common import PRODUCTION

STATUSES = {"PASS", "FAIL", "ERROR"}
CODES = {"PASS": 0, "FAIL": 1, "ERROR": 2}
ORDER = ("A", "B", "B", "A", "A", "B")
RAW_FIELDS = {"check_stdout_b64", "check_stderr_b64", "check_stdout_sha256", "check_stderr_sha256", "check_output_overflow"}
FROZEN_ALIASES = {"importlib._bootstrap": "_frozen_importlib", "importlib._bootstrap_external": "_frozen_importlib_external", "os.path": "posixpath"}


class IncompleteExecutionError(ValueError):
    """Approved check aborted setup/assignment; evidence is retained but ineligible."""


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def same_json(left, right):
    # Python equality conflates True/1 and integer/float metadata. Bind JSON
    # types exactly; raw lookup equality remains in verify_evaluation.
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def fields(value, required, optional=()):
    require(type(value) is dict and set(required) <= set(value) <= set(required) | set(optional), "EVIDENCE_FIELDS")


def decode_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("NONFINITE_JSON")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)


def aggregate(statuses):
    require(bool(statuses) and all(s in STATUSES for s in statuses), "INVALID_STATUS")
    return "ERROR" if "ERROR" in statuses else ("FAIL" if "FAIL" in statuses else "PASS")


def observation(obs):
    require(type(obs) is dict and obs.get("kind") in ("value", "KeyError", "error"), "OBSERVATION_KIND")
    if obs["kind"] == "value":
        fields(obs, {"kind", "value"})
        v = obs["value"]
        if type(v) is dict:
            if v.get("kind") == "text":
                fields(v, {"kind", "prefix", "truncated"})
                require(type(v["prefix"]) is str and len(v["prefix"]) <= 160 and type(v["truncated"]) is bool, "TEXT_DIAGNOSTIC")
            else:
                fields(v, {"kind", "omitted"})
                require(v["kind"] in ("opaque", "large_integer", "nonfinite_float") and v["omitted"] is True, "OPAQUE_DIAGNOSTIC")
        else:
            require(v is None or type(v) in (bool, int, float), "UNSAFE_DIAGNOSTIC")
            require(type(v) is not float or math.isfinite(v), "NONFINITE_DIAGNOSTIC")
            require(type(v) is not int or v.bit_length() <= 256, "UNBOUNDED_DIAGNOSTIC")
    elif obs["kind"] == "error":
        fields(obs, {"kind", "stage"})
        require(obs["stage"] in ("membership", "lookup"), "OBSERVATION_ERROR_STAGE")
    else:
        fields(obs, {"kind"})


def membership_observation(obs):
    observation(obs)
    require(obs.get("kind") == "error" or (obs.get("kind") == "value" and type(obs.get("value")) is bool), "MEMBERSHIP_NOT_BOOLEAN")


def verify_raw_check(envelope, context):
    require(RAW_FIELDS <= set(envelope) and type(envelope["check_output_overflow"]) is bool, "RAW_CHECK_FIELDS")
    streams = []
    for name in ("stdout", "stderr"):
        encoded = envelope["check_" + name + "_b64"]
        require(type(encoded) is str, "RAW_CHECK_ENCODING")
        raw = base64.b64decode(encoded, validate=True)
        require(base64.b64encode(raw).decode("ascii") == encoded, "NONCANONICAL_BASE64")
        require(len(raw) <= context["check_" + name + "_limit"] and
                hashlib.sha256(raw).hexdigest() == envelope["check_" + name + "_sha256"], "RAW_CHECK_HASH_OR_BOUND")
        streams.append(raw)
    return tuple(streams)


def verify_nonfile_modules(modules):
    require(type(modules) is dict and {"sys", "builtins"} <= set(modules), "NONFILE_MODULE_INVENTORY")
    for name, record in modules.items():
        fields(record, {"kind", "canonical_name"})
        canonical = record["canonical_name"]
        require(type(canonical) is str, "NONFILE_MODULE_NAME")
        if record["kind"] == "built-in":
            require(name == canonical and bool(_imp.is_builtin(name)), "UNKNOWN_BUILTIN_MODULE")
        elif record["kind"] == "frozen":
            require(bool(_imp.is_frozen(canonical)) and (name == canonical or FROZEN_ALIASES.get(name) == canonical), "UNKNOWN_FROZEN_MODULE")
        else:
            raise ValueError("UNKNOWN_NONFILE_MODULE_KIND")


def verify_evaluation(evaluation, obs, expected):
    fields(evaluation, {"status"}, {"error_stage"})
    require(evaluation["status"] in STATUSES, "ASSERTION_STATUS")
    observation(obs)
    observation(expected)
    if obs["kind"] == "error":
        require(evaluation == {"status": "ERROR", "error_stage": obs["stage"]}, "OBSERVATION_ERROR_CLASSIFICATION")
        return
    if obs["kind"] != expected["kind"]:
        wanted = "FAIL"
    elif expected["kind"] == "KeyError":
        wanted = "PASS"
    elif type(obs["value"]) is dict and obs["value"].get("kind") == "opaque":
        # Raw equality was evaluated by the hash-bound check. Opaque diagnostics
        # deliberately cannot be independently re-evaluated in this parent.
        if evaluation["status"] == "ERROR":
            require(evaluation == {"status": "ERROR", "error_stage": "equality_evaluation"}, "EQUALITY_ERROR_CLASSIFICATION")
        else:
            require(set(evaluation) == {"status"}, "UNEXPECTED_EVALUATION_ERROR")
        return
    elif type(obs["value"]) is dict:
        wanted = "FAIL"  # text/nonfinite/large integer cannot equal fixture integers
    else:
        wanted = "PASS" if obs["value"] == expected["value"] else "FAIL"
    require(evaluation == {"status": wanted}, "ASSERTION_CLASSIFICATION_MISMATCH")


def expected_assertions(scenario, recipe):
    if scenario["expected_target"] == "absent":
        entries = [("C1", "target_absent", "target_membership", {"kind": "value", "value": False}),
                   ("C2", "target_lookup_KeyError", "target_lookup", {"kind": "KeyError"})]
    else:
        entries = [("C4", "target_present", "target_membership", {"kind": "value", "value": True}),
                   ("C4", "target_reads_replacement", "target_lookup", {"kind": "value", "value": scenario["replacement"]})]
    return entries + [("C3", "survivor_unchanged", "survivor_lookup", {"kind": "value", "value": recipe["survivor_value"]})]


def verify_imports(imports, context):
    require(type(imports) is dict and "cachetools" in imports, "MISSING_IMPORT_EVIDENCE")
    root = Path(context["snapshot_root"])
    for name, record in imports.items():
        fields(record, {"path", "sha256"})
        require(name == "cachetools" or name.startswith("cachetools."), "UNEXPECTED_PACKAGE_IMPORT")
        path = Path(record["path"])
        require(path.is_absolute() and path.is_relative_to(root), "WRONG_IMPORT_ROOT")
        relative = path.relative_to(root).as_posix()
        require(relative.startswith("src/cachetools/") and relative in context["manifest"]["files"], "WRONG_IMPORT_FILE")
        require(record["sha256"] == context["manifest"]["files"][relative]["sha256"], "WRONG_IMPORT_HASH")
    require(imports["cachetools"]["path"] == str(root / PRODUCTION), "WRONG_PACKAGE_IMPORT")


def verify_result(result, exit_code, context):
    fields(result, {"status", "contract_sha256", "recipe_sha256", "template_sha256", "scenarios",
                   "imports_before", "imports_after", "snapshot_verified_before_and_after", "revision", "manifest_sha256"}, {"error"})
    require(result["status"] in STATUSES and type(exit_code) is int and exit_code == CODES[result["status"]], "EXIT_STATUS_MISMATCH")
    for key in ("contract_sha256", "recipe_sha256", "template_sha256", "revision", "manifest_sha256"):
        require(result[key] == context[key], "RESULT_BINDING_MISMATCH: " + key)
    require(result["snapshot_verified_before_and_after"] is True, "SNAPSHOT_VERIFICATION_MISSING")
    verify_imports(result["imports_before"], context)
    verify_imports(result["imports_after"], context)
    recipe = context["recipe"]
    require(type(result["scenarios"]) is list and len(result["scenarios"]) == 4, "SCENARIO_COUNT")
    incomplete = False
    count = 0
    for actual, scenario in zip(result["scenarios"], recipe["scenarios"]):
        fields(actual, {"scenario_id", "historical_role", "assertions", "observations", "status"},
               {"setup_observations", "setup_evaluations", "error"})
        require(actual["scenario_id"] == scenario["id"] and actual["historical_role"] == scenario["historical_role"], "SCENARIO_ID_OR_ORDER")
        require(type(actual["assertions"]) is list, "ASSERTION_LIST")
        if not actual["assertions"] and actual["status"] == "ERROR" and "error" in actual:
            fields(actual["error"], {"stage", "reason"})
            require(actual["error"]["stage"] in ("setup", "assignment") and
                    actual["error"]["reason"] in ("precondition_not_established", "unexpected_exception") and
                    actual["observations"] == {}, "INVALID_PARTIAL_ERROR")
            incomplete = True
            continue
        require("error" not in actual, "UNEXPECTED_SCENARIO_ERROR")
        fields(actual["observations"], {"target_membership", "target_lookup", "survivor_lookup"})
        setup = {"target_membership": {"kind": "value", "value": scenario["initial_target_present"]},
                 "target_lookup": {"kind": "value", "value": recipe["old_value"]} if scenario["initial_target_present"] else {"kind": "KeyError"},
                 "survivor_membership": {"kind": "value", "value": True},
                 "survivor_lookup": {"kind": "value", "value": recipe["survivor_value"]}}
        fields(actual.get("setup_observations"), set(setup))
        fields(actual.get("setup_evaluations"), set(setup))
        for name, expected in setup.items():
            if name.endswith("membership"):
                membership_observation(actual["setup_observations"][name])
            verify_evaluation(actual["setup_evaluations"][name], actual["setup_observations"][name], expected)
            require(actual["setup_evaluations"][name]["status"] == "PASS", "SETUP_NOT_PASSED")
        expected = expected_assertions(scenario, recipe)
        require(len(actual["assertions"]) == len(expected), "ASSERTION_COUNT")
        for assertion, (claim, identity, observed_name, expected_obs) in zip(actual["assertions"], expected):
            fields(assertion, {"claim_id", "assertion_id", "status", "observed", "expected"}, {"error_stage"})
            require((assertion["claim_id"], assertion["assertion_id"]) == (claim, identity), "ASSERTION_ID_OR_ORDER")
            require(assertion["expected"] == expected_obs and assertion["observed"] == actual["observations"][observed_name], "ASSERTION_OBSERVATION_BINDING")
            if observed_name == "target_membership":
                obs = assertion["observed"]
                membership_observation(obs)
            verify_evaluation({k: assertion[k] for k in ("status", "error_stage") if k in assertion}, assertion["observed"], assertion["expected"])
            count += 1
        require(actual["status"] == aggregate([a["status"] for a in actual["assertions"]]), "SCENARIO_CLASSIFICATION_MISMATCH")
    require(result["status"] == aggregate([s["status"] for s in result["scenarios"]]), "AGGREGATE_CLASSIFICATION_MISMATCH")
    require("error" not in result, "UNEXPECTED_RESULT_ERROR")
    if incomplete:
        raise IncompleteExecutionError("INCOMPLETE_SETUP_OR_ASSIGNMENT_ERROR: not twelve assertions; ineligible")
    require(count == 12, "SCOPED_ASSERTION_COUNT")
    return result


def verify_envelope(raw, exit_code, context, pid):
    envelope = decode_json(raw)
    fields(envelope, {"kind", "interpreter", "pid", "check_sha256", "manifest_sha256", "module_files", "nonfile_modules",
                      "result", "environment", "cwd", "invocation_id", "request_sha256"} | RAW_FIELDS)
    require(envelope["kind"] == "hindsight_trusted_execution_v2", "WRONG_EXECUTION_KIND")
    require(envelope["invocation_id"] == context["invocation_id"] and envelope["request_sha256"] == context["request_sha256"], "INVOCATION_BINDING_MISMATCH")
    stdout, stderr = verify_raw_check(envelope, context)
    require(envelope["check_output_overflow"] is False and not stderr, "CHECK_STREAM_FAILURE")
    original = decode_json(stdout)
    require(json.dumps(original, sort_keys=True, allow_nan=False) == json.dumps(envelope["result"], sort_keys=True, allow_nan=False), "RAW_RESULT_DISAGREEMENT")
    verify_nonfile_modules(envelope["nonfile_modules"])
    require(not set(envelope["module_files"]) & set(envelope["nonfile_modules"]), "DUPLICATED_MODULE_KIND")
    require(type(envelope["pid"]) is int and envelope["pid"] == pid, "WORKER_PID_MISMATCH")
    require(same_json(envelope["interpreter"], context["interpreter"]), "INTERPRETER_MISMATCH")
    require(envelope["environment"] == context["environment"] and envelope["cwd"] == context["cwd"], "ENVIRONMENT_OR_CWD_MISMATCH")
    require(envelope["check_sha256"] == context["check_sha256"] and envelope["manifest_sha256"] == context["manifest_sha256"], "WORKER_BINDING_MISMATCH")
    require(type(envelope["module_files"]) is dict and bool(envelope["module_files"]), "MISSING_MODULE_INVENTORY")
    for name, record in envelope["module_files"].items():
        fields(record, {"path", "sha256"})
        path = Path(record["path"])
        require(path.is_absolute() and path == path.resolve(), "NONCANONICAL_MODULE_PATH")
        package = name == "cachetools" or name.startswith("cachetools.")
        if package:
            verify_imports({"cachetools": envelope["result"]["imports_after"]["cachetools"], name: record}, context)
        else:
            require(path == Path(context["worker_path"]) if name == "__main__" else (
                path.is_relative_to(Path(context["stdlib_root"])) and not any(p in ("site-packages", "dist-packages") for p in path.parts)), "UNEXPECTED_MODULE_ORIGIN")
            require(path.is_file() and record["sha256"] == context["hash_file"](path), "MODULE_HASH_MISMATCH")
    require("__main__" in envelope["module_files"] and "cachetools" in envelope["module_files"], "REQUIRED_MODULE_INVENTORY")
    require(envelope["module_files"]["__main__"]["sha256"] == context["worker_sha256"], "WORKER_SOURCE_HASH")
    require({name: value for name, value in envelope["module_files"].items()
             if name == "cachetools" or name.startswith("cachetools.")} == envelope["result"]["imports_after"],
            "PACKAGE_INVENTORY_DISAGREEMENT")
    verify_result(envelope["result"], exit_code, context)
    return envelope


def verify_collection(record, launch, number, label):
    """Recheck raw evidence against separately retained parent launch/collection data."""
    context = launch["context"]
    require(record.get("evidence_valid") is True, "EVIDENCE_NOT_VERIFIED")
    require(record.get("transport") == launch["transport"] == "COMPLETED", "TRANSPORT_NOT_COMPLETED")
    require(record["label"] == launch["label"] == label and type(record["invocation"]) is int and
            record["invocation"] == number and type(record["pair"]) is int and record["pair"] == (number + 1) // 2, "INVOCATION_ORDER_OR_PAIR")
    for key in ("invocation_id", "request_sha256", "environment", "cwd", "interpreter", "stdout_limit", "stderr_limit"):
        require(same_json(record[key], context[key]), "COLLECTION_CONTEXT_MISMATCH: " + key)
    for key in ("pid", "exit_code", "elapsed_seconds", "timeout_seconds", "command", "worker_sha256", "approval_bindings"):
        require(same_json(record[key], launch[key]), "COLLECTION_METADATA_MISMATCH: " + key)
    require(type(record["elapsed_seconds"]) in (int, float) and math.isfinite(record["elapsed_seconds"]) and
            0 <= record["elapsed_seconds"] <= record["timeout_seconds"], "EXECUTION_DURATION")
    for name in ("stdout", "stderr"):
        limit = context[name + "_limit"]
        path = Path(launch[name + "_path"])
        require(path.is_absolute() and path == path.resolve() and path.is_file() and not path.is_symlink() and
                path.stat().st_size <= limit, "RAW_STREAM_PATH_OR_BOUND")
        raw = path.read_bytes()
        require(len(raw) <= limit and hashlib.sha256(raw).hexdigest() == launch[name + "_sha256"] == record[name + "_sha256"], "RAW_STREAM_HASH")
        require(record[name] == raw.decode("utf-8", errors="replace"), "RAW_STREAM_DIAGNOSTIC_MISMATCH")
        if name == "stdout":
            stdout = raw
        else:
            require(not raw, "UNEXPECTED_STDERR")
    envelope = verify_envelope(stdout, record["exit_code"], context, launch["pid"])
    require(same_json(envelope, record["worker"]) and record["status"] == envelope["result"]["status"], "COLLECTED_RESULT_MISMATCH")
    return envelope["result"]


def evaluate_history(runs, launches):
    """Acceptance only: requires independent per-invocation launch/collection ledger."""
    reasons, fingerprints, seen = [], {"A": [], "B": []}, set()
    if type(runs) is not list or type(launches) is not list or len(runs) != 6 or len(launches) != 6:
        return {"accepted": False, "stable": False, "reasons": ["INCOMPLETE_PROTOCOL_OR_LAUNCH_LEDGER"],
                "active": False, "activation": "NOT_ACTIVATED; separate Checkpoint D decision required"}
    for number, (record, launch, label) in enumerate(zip(runs, launches, ORDER), 1):
        try:
            context = launch["context"]
            require(type(context["invocation_id"]) is str and context["invocation_id"] not in seen, "DUPLICATED_INVOCATION")
            seen.add(context["invocation_id"])
            require(record.get("status") in ("PASS", "FAIL"), "EXECUTION_OR_INTEGRITY_FAILURE")
            result = verify_collection(record, launch, number, label)
        except (ValueError, OSError, KeyError, TypeError, AttributeError, RecursionError) as exc:
            reasons.append(f"INVOCATION_{number}_INVALID_COLLECTED_EVIDENCE: " + str(exc))
            continue
        fingerprint = [(s["scenario_id"], s["status"], [(a["claim_id"], a["assertion_id"], a["status"], a["observed"]) for a in s["assertions"]]) for s in result["scenarios"]]
        fingerprints[label].append(fingerprint)
        for scenario in result["scenarios"]:
            wanted = "FAIL" if label == "A" and scenario["historical_role"] == "discriminator" else "PASS"
            if scenario["status"] != wanted:
                reasons.append(f"INVOCATION_{number}_{scenario['scenario_id']}_NONDISCRIMINATING")
            if label == "A" and scenario["historical_role"] == "discriminator":
                failed = {a["claim_id"] for a in scenario["assertions"] if a["status"] == "FAIL"}
                if not failed or not failed <= {"C1", "C2"}:
                    reasons.append(f"INVOCATION_{number}_WRONG_DESIGNATED_FAILURE")
    stable = True
    for label, values in fingerprints.items():
        if len(values) != 3:
            stable = False
            reasons.append("MISSING_VALID_REPEATS_" + label)
        if values and any(value != values[0] for value in values[1:]):
            stable = False
            reasons.append("UNSTABLE_" + label)
    return {"accepted": not reasons, "stable": stable, "reasons": reasons, "active": False,
            "activation": "NOT_ACTIVATED; separate Checkpoint D decision required"}
