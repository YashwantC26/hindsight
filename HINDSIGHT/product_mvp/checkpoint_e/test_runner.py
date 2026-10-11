"""Synthetic E tests only. Never execute real B/R/N or write live authorization."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import runner as e

# Only a literal fixture builder is imported, not an execution entry point.
sys.path.insert(0, str(e.MVP))
from test_historical_runner import synthetic_envelope, with_raw

REAL_ROOT, REAL_LIVE = e.ROOT, e.LIVE


def save(path, value):
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True, allow_nan=False).encode() + b"\n")


def assert_disclosure(test, result):
    test.assertEqual(result["limitations"], e.LIMITATIONS)
    test.assertIn("INTENTIONALLY_SEEDED_REGRESSION", result["limitations"])
    test.assertIn("deliberately seeded for demonstration", result["limitations"][1])
    test.assertIn("not evidence of autonomous discovery of a naturally occurring AI-generated bug", result["limitations"][1])
    test.assertTrue(any("no hostile-code or network isolation" in s for s in result["limitations"]))
    test.assertTrue(any("no strong identity or remote execution attestation" in s for s in result["limitations"]))


class SyntheticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.decision_pin = e.sha(e.raw(REAL_LIVE / e.activation.DECISION))
        cls.runner_pin = e.sha(e.raw(REAL_ROOT / "runner.py"))
        cls.active, cls.trust = e.activation_gate(cls.decision_pin, cls.runner_pin)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name).resolve()
        self.root = self.workspace / "HINDSIGHT/product_mvp/checkpoint_e"
        self.live = self.root.parent / "runs/attempt01"
        self.root.mkdir(parents=True)
        for name in ("runner.py", "DESIGN.md", "evidence.schema.json"):
            shutil.copyfile(REAL_ROOT / name, self.root / name)
        shutil.copytree(REAL_ROOT / "candidates", self.root / "candidates")
        shutil.copytree(REAL_LIVE / "snapshots/B", self.live / "snapshots/B")
        shutil.copyfile(REAL_LIVE / e.activation.DECISION, self.live / e.activation.DECISION)
        executable = self.workspace / ".venv/bin/python"
        executable.parent.mkdir(parents=True)
        executable.symlink_to(Path(sys.executable).resolve())
        for name, value in (("ROOT", self.root), ("WORKSPACE", self.workspace), ("LIVE", self.live)):
            guard = patch.object(e, name, value); guard.start(); self.addCleanup(guard.stop)
        gate = patch.object(e, "activation_gate", return_value=(copy.deepcopy(self.active), copy.deepcopy(self.trust)))
        self.gate = gate.start(); self.addCleanup(gate.stop)
        capture = patch.object(e.historical, "capture_process", side_effect=self.capture)
        self.capture_mock = capture.start(); self.addCleanup(capture.stop)
        for name in ("historical_validation", "invocation"):
            guard = patch.object(e.historical, name, side_effect=AssertionError("HISTORICAL EXECUTION FORBIDDEN"))
            guard.start(); self.addCleanup(guard.stop)
        self.prepared = self.root / "prepared/synthetic_v1"
        self.base_kwargs = {"decision_pin": self.decision_pin, "runner_pin": self.runner_pin}
        prepared = e.prepare(self.prepared, **self.base_kwargs)
        self.bundle_pin = prepared["bundle_sha256"]
        self.kwargs = {**self.base_kwargs, "bundle_pin": self.bundle_pin}
        self.auth_pin = None; self.synthetic_mutator = None

    def capture(self, command, cwd, timeout, stdout_limit, stderr_limit):
        destination = Path(command[command.index("--request") + 1]).parent
        context = e.read(destination / "launch-context.json")
        number = int(destination.name[-2:]); label = e.PLAN["order"][number - 1]
        envelope = synthetic_envelope(context, failing=label == "R")
        envelope["pid"] = 20000 + number
        if self.synthetic_mutator:
            self.synthetic_mutator(envelope, number, label)
        with_raw(envelope)
        return {"transport": "COMPLETED", "pid": envelope["pid"], "exit_code": {"PASS": 0, "FAIL": 1, "ERROR": 2}[envelope["result"]["status"]],
                "stdout": json.dumps(envelope, sort_keys=True, allow_nan=False).encode(), "stderr": b"", "elapsed_seconds": 0.01}

    def authorize(self, **changes):
        metadata = {"reviewer": "Synthetic reviewer", "review_minutes": 5.0,
                    "note": "Synthetic temporary fixture only", "confirmed": True, **changes}
        result = e.authorize(self.prepared, **self.kwargs, **metadata)
        self.auth_pin = result["authorization_sha256"]
        return result

    def execute(self):
        if self.auth_pin is None:
            self.authorize()
        result = e.execute(self.prepared, **self.kwargs, authorization_pin=self.auth_pin, confirmed=True)
        assert_disclosure(self, result)
        assert_disclosure(self, e.read(self.prepared / "execution-v1/report.json"))
        return result

    def verify(self):
        result = e.verify_evidence(self.prepared, **self.kwargs, authorization_pin=self.auth_pin)
        assert_disclosure(self, result)
        return result

    def cli_verify(self, **pins):
        options = {"runner-sha256": self.runner_pin, "activation-decision-sha256": self.decision_pin,
                   "prepared-dir": str(self.prepared), "bundle-sha256": self.bundle_pin,
                   "authorization-sha256": self.auth_pin, **pins}
        argv = ["verify-evidence"]
        for name, value in options.items():
            argv.extend(["--" + name, value])
        with patch("sys.stdout", io.StringIO()) as output:
            code = e.main(argv)
        result = json.loads(output.getvalue())
        assert_disclosure(self, result)
        return code, result

    def test_prepare_and_preflight_never_execute(self):
        bundle, _ = e.verify_prepared(self.prepared, **self.kwargs)
        self.assertEqual(bundle["baseline_revision"], e.BASELINE)
        self.assertNotEqual(bundle["manifests"]["R"]["revision"], e.activation.FIXED)
        self.capture_mock.assert_not_called()
        self.assertFalse((self.prepared / "authorization.json").exists())

    def test_equal_content_independent_files_accepted(self):
        files = [self.prepared / "snapshots" / label / "src/cachetools/keys.py" for label in ("B", "R", "N")]
        self.assertEqual(len({p.read_bytes() for p in files}), 1)
        self.assertEqual(len({(p.stat().st_dev, p.stat().st_ino) for p in files}), 3)
        e.verify_prepared(self.prepared, **self.kwargs)
        self.capture_mock.assert_not_called()

    def test_keys_hard_link_alias_across_prepared_trees_rejected(self):
        baseline = self.prepared / "snapshots/B/src/cachetools/keys.py"
        candidate = self.prepared / "snapshots/R/src/cachetools/keys.py"
        candidate.unlink(); os.link(baseline, candidate, follow_symlinks=False)
        self.assertEqual(baseline.stat().st_ino, candidate.stat().st_ino)
        # Existing content/file-set/mode checks alone accept these bytes.
        bundle = e.read(self.prepared / "bundle.json")
        for label in ("B", "R", "N"):
            e.verify_snapshot(self.prepared / "snapshots" / label, bundle["manifests"][label])
        with self.assertRaisesRegex(ValueError, "SHARED_SNAPSHOT_FILE_IDENTITY"):
            e.verify_prepared(self.prepared, **self.kwargs)
        self.capture_mock.assert_not_called()
        self.assertFalse((self.prepared / "authorization.json").exists())

    def test_no_execution_without_authorization_or_confirmation(self):
        for confirmed in (False, True):
            with self.subTest(confirmed=confirmed), self.assertRaises((ValueError, OSError)):
                e.execute(self.prepared, **self.kwargs, authorization_pin="0" * 64, confirmed=confirmed)
        self.capture_mock.assert_not_called()
        self.assertFalse((self.prepared / "execution-v1").exists())

    def test_missing_or_invalid_human_metadata_no_authorization(self):
        for args in ({"confirmed": False}, {"confirmed": 1}, {"reviewer": " "}, {"review_minutes": 0},
                     {"review_minutes": True}, {"review_minutes": float("inf")}, {"note": ""}):
            with self.subTest(args=args), self.assertRaises((ValueError, TypeError)):
                self.authorize(**args)
        self.assertFalse((self.prepared / "authorization.json").exists())

    def test_stale_or_wrong_activation_and_ancestry_blocks(self):
        for reason in ("STALE_ACTIVATION_DECISION", "EFFECTIVE_ACTIVE_REQUIRED", "DIRECT_PARENT_MISMATCH"):
            self.gate.side_effect = ValueError(reason)
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                self.authorize()
        self.capture_mock.assert_not_called()

    def test_wrong_candidate_diff_hash(self):
        p = self.root / "candidates/R.patch"; p.write_bytes(p.read_bytes() + b"bad")
        with self.assertRaisesRegex(ValueError, "DIFF_CHANGED"):
            self.authorize()

    def test_wrong_candidate_source_manifest_and_extra_file(self):
        p = self.prepared / "snapshots/R/src/cachetools/__init__.py"; original = p.read_bytes()
        p.write_bytes(original + b"\n")
        with self.assertRaisesRegex(ValueError, "SNAPSHOT_SOURCE"):
            self.authorize()
        p.write_bytes(original)
        p = self.prepared / "snapshots/N/EXTRA"; p.write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "FILE_SET"):
            self.authorize()

    def test_candidate_manifest_relabeling_rejected(self):
        p = self.prepared / "manifest-R.json"; value = e.read(p); value["revision"] = "historical-A"; save(p, value)
        with self.assertRaisesRegex(ValueError, "MANIFEST_CHANGED"):
            self.authorize()

    def test_wrong_bundle_baseline_check_and_runner_bindings(self):
        p = self.prepared / "bundle.json"; original = p.read_bytes()
        for field, value in (("baseline_revision", "WRONG"), ("runner_sha256", "0" * 64)):
            obj = json.loads(original); obj[field] = value; save(p, obj)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "STALE_PREPARED"):
                e.verify_prepared(self.prepared, **{**self.kwargs, "bundle_pin": e.sha(p.read_bytes())})
        obj = json.loads(original); obj["activation"]["verified"]["trust_pins"]["check_sha256"] = "0" * 64; save(p, obj)
        with self.assertRaisesRegex(ValueError, "STALE_PREPARED"):
            e.verify_prepared(self.prepared, **{**self.kwargs, "bundle_pin": e.sha(p.read_bytes())})

    def test_symlink_and_traversal_rejected(self):
        p = self.prepared / "snapshots/R/src/cachetools/__init__.py"; original = p.read_bytes()
        p.unlink(); target = self.root / "outside.py"; target.write_bytes(original); p.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "SYMLINK"):
            self.authorize()
        for name in (str(self.prepared / "../synthetic_v1"), str(self.root.parent / "runs/attempt01")):
            with self.subTest(name=name), self.assertRaises(ValueError):
                e.prepared_path(name)

    def test_patch_path_context_and_duplicate_hunk_rejected(self):
        source = (self.live / "snapshots/B/src/cachetools/__init__.py").read_bytes()
        patch_raw = (self.root / "candidates/R.patch").read_bytes()
        for bad in (patch_raw.replace(b"a/src/cachetools", b"a/../cachetools"),
                    patch_raw.replace(b"self.timer", b"UNKNOWN_TIMER"), patch_raw + b"@@ -637,6 +637,7 @@\n"):
            with self.subTest(bad=bad[:70]), self.assertRaises(ValueError):
                e.apply_patch(source, bad)

    def test_duplicate_json_and_partial_authorization(self):
        self.authorize(); p = self.prepared / "authorization.json"
        for data in (b'{"schema_version":1,"schema_version":1}', b'{}', b'{"review_minutes":NaN}'):
            p.write_bytes(data)
            with self.assertRaises(ValueError):
                e.execute(self.prepared, **self.kwargs, authorization_pin=e.sha(data), confirmed=True)
        self.capture_mock.assert_not_called()

    def test_authorization_binding_drift_and_wrong_pin(self):
        self.authorize(); p = self.prepared / "authorization.json"; obj = e.read(p)
        obj["bindings"]["plan"]["timeout_seconds"] = 100; save(p, obj)
        for auth_pin in (self.auth_pin, e.sha(p.read_bytes())):
            with self.assertRaises(ValueError):
                e.execute(self.prepared, **self.kwargs, authorization_pin=auth_pin, confirmed=True)
        self.capture_mock.assert_not_called()

    def test_synthetic_benign_pass_and_seeded_detection(self):
        result = self.execute()
        assert_disclosure(self, result)
        assert_disclosure(self, e.read(self.prepared / "execution-v1/report.json"))
        self.assertEqual(self.capture_mock.call_count, 9)
        self.assertEqual(result["baseline"], "PASS")
        self.assertEqual(result["candidates"]["R"]["status"], "REGRESSION_DETECTED")
        self.assertEqual(result["candidates"]["N"]["status"], "PASS")
        self.assertTrue(result["demo_expectations_met"])
        self.assertEqual({v["claim_id"] for v in result["candidates"]["R"]["violations"]}, {"C1", "C2"})
        before = {p: p.read_bytes() for p in self.prepared.rglob("*") if p.is_file()}
        self.assertEqual(self.verify(), result)
        self.assertEqual(before, {p: p.read_bytes() for p in self.prepared.rglob("*") if p.is_file()})
        self.assertEqual(self.capture_mock.call_count, 9)

    def test_completed_pass_report_keeps_disclosure_and_expectations_false(self):
        def mutate(envelope, number, label):
            if label == "R":
                context = e.read(self.prepared / "execution-v1" / f"invocation-{number:02}/launch-context.json")
                passing = synthetic_envelope(context, False); passing["pid"] = envelope["pid"]
                envelope.clear(); envelope.update(passing)
        self.synthetic_mutator = mutate
        result = self.execute()
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["demo_expectations_met"])
        code, verified = self.cli_verify()
        self.assertEqual(code, 0); self.assertEqual(verified, result)
        self.assertEqual(self.capture_mock.call_count, 9)

    def test_no_overwrite_authorization_preparation_or_execution(self):
        self.execute(); p = self.prepared / "execution-v1/report.json"; original = p.read_bytes()
        for operation in (self.authorize, self.execute, lambda: e.prepare(self.prepared, **self.base_kwargs)):
            with self.assertRaises((ValueError, FileExistsError)):
                operation()
        self.assertEqual(p.read_bytes(), original)
        self.assertEqual(self.capture_mock.call_count, 9)

    def test_partial_attempt_blocks_retry_and_verifies_inconclusive(self):
        self.authorize(); (self.prepared / "execution-v1").mkdir()
        result = self.verify(); assert_disclosure(self, result)
        self.assertEqual(result["status"], "INCONCLUSIVE")
        code, result = self.cli_verify()
        self.assertEqual(code, 2); self.assertEqual(result["status"], "INCONCLUSIVE")
        with self.assertRaises(FileExistsError):
            self.execute()
        self.capture_mock.assert_not_called()

    def test_cli_invalid_pins_are_blocked_with_disclosure(self):
        self.authorize()
        for name in ("bundle-sha256", "authorization-sha256"):
            for value in ("0" * 64, "malformed"):
                with self.subTest(pin=name, value=value):
                    code, result = self.cli_verify(**{name: value})
                    self.assertEqual(code, 2); self.assertEqual(result["state"], "BLOCKED")
                    self.assertFalse(result["regression_detected"])
        self.capture_mock.assert_not_called()

    def test_cli_failed_preflight_has_disclosure_without_execution(self):
        self.gate.side_effect = ValueError("EFFECTIVE_ACTIVE_REQUIRED")
        with patch("sys.stdout", io.StringIO()) as output:
            code = e.main(["preflight", "--runner-sha256", self.runner_pin,
                           "--activation-decision-sha256", self.decision_pin])
        result = json.loads(output.getvalue()); assert_disclosure(self, result)
        self.assertEqual(code, 2); self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["reason"], "EFFECTIVE_ACTIVE_REQUIRED")
        self.assertFalse(result["regression_detected"])
        self.capture_mock.assert_not_called()

    def test_cli_invalidated_evidence_retains_disclosure(self):
        self.execute()
        (self.prepared / "execution-v1/invocation-01/stdout.bin").write_bytes(b"changed")
        code, result = self.cli_verify()
        self.assertEqual(code, 2); self.assertEqual(result["state"], "BLOCKED")
        self.assertEqual(result["reason"], "EVIDENCE_INVENTORY_CHANGED")
        self.assertFalse(result["regression_detected"])
        self.assertEqual(self.capture_mock.call_count, 9)

    def test_response_metadata_preserves_every_classification(self):
        for status in ("PASS", "REGRESSION_DETECTED", "INCONCLUSIVE", "BLOCKED", "ERROR", "UNSTABLE", "INVALIDATED"):
            original = {"status": status, "reason": "unchanged", "demo_expectations_met": False}
            result = e.response(original); assert_disclosure(self, result)
            self.assertEqual({k: result[k] for k in original}, original)
            result["limitations"].clear()
            self.assertTrue(e.LIMITATIONS)  # Each response owns its metadata list.

    def test_missing_extra_swapped_and_duplicate_evidence_rejected(self):
        self.execute(); root = self.prepared / "execution-v1"
        p = root / "invocation-01/stdout.bin"; original = p.read_bytes(); p.unlink()
        with self.assertRaises(ValueError):
            self.verify()
        p.write_bytes(original); extra = root / "EXTRA"; extra.write_bytes(b"x")
        with self.assertRaises(ValueError):
            self.verify()
        extra.unlink(); p.write_bytes((root / "invocation-02/stdout.bin").read_bytes())
        with self.assertRaises(ValueError):
            self.verify()
        p.write_bytes(b'{"x":1,"x":2}')
        with self.assertRaises(ValueError):
            self.verify()

    def test_claimed_summary_cannot_override_recomputed_evidence(self):
        self.execute(); p = self.prepared / "execution-v1/report.json"; report = e.read(p)
        report["classification"]["candidates"]["N"]["status"] = "REGRESSION_DETECTED"; save(p, report)
        with self.assertRaisesRegex(ValueError, "CLASSIFICATION"):
            self.verify()

    def test_wrong_context_metadata_even_when_inventory_repinned(self):
        self.execute(); root = self.prepared / "execution-v1"; p = root / "invocation-01/launch-context.json"
        context = e.read(p); context["interpreter"]["sha256"] = "0" * 64; save(p, context)
        report_path = root / "report.json"; report = e.read(report_path)
        report["evidence_inventory"] = e.evidence_inventory(root); save(report_path, report)
        with self.assertRaisesRegex(ValueError, "CONTEXT_CHANGED"):
            self.verify()

    def test_duplicate_process_even_when_inventory_repinned(self):
        self.execute(); root = self.prepared / "execution-v1"; p = root / "invocation-02/collection.json"
        obj = e.read(p); obj["pid"] = 20001; save(p, obj)
        report_path = root / "report.json"; report = e.read(report_path)
        report["evidence_inventory"] = e.evidence_inventory(root); save(report_path, report)
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PROCESS|RECORD_DISAGREEMENT"):
            self.verify()

    def test_timeout_output_limit_subprocess_failure_never_detection(self):
        for transport in ("TIMEOUT", "OUTPUT_LIMIT"):
            self.capture_mock.side_effect = lambda *args, t=transport: {"transport": t, "pid": 100 + self.capture_mock.call_count,
                "exit_code": -9, "stdout": b"", "stderr": b"", "elapsed_seconds": 0.02}
            result = self.execute()
            self.assertEqual(result["status"], "ERROR"); self.assertFalse(result["demo_expectations_met"])
            # New temporary version/authorization, never overwrite the first.
            self.prepared = self.root / "prepared" / transport
            self.bundle_pin = e.prepare(self.prepared, **self.base_kwargs)["bundle_sha256"]
            self.kwargs["bundle_pin"] = self.bundle_pin; self.auth_pin = None
        self.capture_mock.side_effect = OSError("synthetic failed spawn")
        result = self.execute(); self.assertEqual(result["status"], "ERROR")
        self.assertFalse(result["demo_expectations_met"])

    def test_unexpected_result_shape_is_error_not_detection(self):
        self.synthetic_mutator = lambda envelope, *args: envelope["result"].update(extra=True)
        result = self.execute(); self.assertEqual(result["status"], "ERROR")
        self.assertFalse(result["demo_expectations_met"])

    def test_setup_and_equality_error_are_not_detection(self):
        def mutate(envelope, number, label):
            if label != "R": return
            scenario = envelope["result"]["scenarios"][0]
            observed = {"kind": "value", "value": {"kind": "opaque", "omitted": True}}
            scenario["observations"]["survivor_lookup"] = observed
            scenario["assertions"][2].update(observed=observed, status="ERROR", error_stage="equality_evaluation")
            scenario["status"] = "ERROR"; envelope["result"]["status"] = "ERROR"
        self.synthetic_mutator = mutate
        result = self.execute(); self.assertEqual(result["candidates"]["R"]["status"], "ERROR")
        self.assertFalse(result["demo_expectations_met"])

    def test_partial_setup_error_is_not_detection(self):
        def mutate(envelope, number, label):
            if label != "R": return
            scenario = envelope["result"]["scenarios"][0]
            scenario.update(assertions=[], observations={}, status="ERROR", error={"stage": "setup", "reason": "precondition_not_established"})
            envelope["result"]["status"] = "ERROR"
        self.synthetic_mutator = mutate
        self.assertEqual(self.execute()["candidates"]["R"]["status"], "ERROR")

    def test_repetition_disagreement_is_unstable(self):
        def mutate(envelope, number, label):
            if number == 5:
                context = e.read(self.prepared / "execution-v1/invocation-05/launch-context.json")
                passing = synthetic_envelope(context, False); passing["pid"] = envelope["pid"]
                envelope.clear(); envelope.update(passing)
        self.synthetic_mutator = mutate
        result = self.execute(); self.assertEqual(result["status"], "UNSTABLE")
        self.assertEqual(result["candidates"]["R"]["status"], "UNSTABLE")

    def test_failing_baseline_is_inconclusive(self):
        def mutate(envelope, number, label):
            if label == "B":
                context = e.read(self.prepared / "execution-v1" / f"invocation-{number:02}/launch-context.json")
                failing = synthetic_envelope(context, True); failing["pid"] = envelope["pid"]
                envelope.clear(); envelope.update(failing)
        self.synthetic_mutator = mutate
        result = self.execute(); self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertFalse(result["demo_expectations_met"])

    def test_precommit_drift_publishes_no_authorization(self):
        original = e.atomic_record
        def drift(path, value, recheck):
            p = self.prepared / "snapshots/N/src/cachetools/__init__.py"; p.write_bytes(b"changed")
            original(path, value, recheck)
        with patch.object(e, "atomic_record", side_effect=drift), self.assertRaises(ValueError):
            self.authorize()
        self.assertFalse((self.prepared / "authorization.json").exists())
        self.assertEqual(list(self.prepared.glob(".pending-*")), [])

    def test_no_writes_to_approved_materials(self):
        before = {p: p.read_bytes() for p in self.live.rglob("*") if p.is_file()}
        self.execute()
        self.assertEqual(before, {p: p.read_bytes() for p in self.live.rglob("*") if p.is_file()})
        with self.assertRaisesRegex(ValueError, "WRITE_OUTSIDE"):
            e.write_raw(self.live / "FORBIDDEN", b"no")

    def test_cli_missing_confirmation_duplicate_options_and_abbreviation(self):
        for args in (["execute"], ["preflight", "--runner", self.runner_pin],
                     ["preflight", "--runner-sha256", self.runner_pin, "--runner-sha256", self.runner_pin]):
            with self.subTest(args=args), patch("sys.stderr", io.StringIO()) as error, patch("sys.stdout", io.StringIO()) as output:
                with self.assertRaises(SystemExit) as raised:
                    e.main(args)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("error:", error.getvalue())
                result = json.loads(output.getvalue()); assert_disclosure(self, result)
                self.assertEqual(result["state"], "BLOCKED")
                self.assertFalse(result["regression_detected"])
        self.capture_mock.assert_not_called()


class RealReadOnlyAndCollectorTests(unittest.TestCase):
    def test_real_prepared_bundle_inspection_without_execution(self):
        prepared = REAL_ROOT / "prepared/demo-v1"
        if not prepared.exists():
            self.skipTest("Live preparation is optional; synthetic preparation remains covered.")
        decision = e.sha(e.raw(REAL_LIVE / e.activation.DECISION)); implementation = e.sha(e.raw(REAL_ROOT / "runner.py"))
        bundle_pin = e.sha(e.raw(prepared / "bundle.json"))
        before = {p: p.read_bytes() for p in prepared.rglob("*") if p.is_file()}
        with patch.object(e.historical, "capture_process", side_effect=AssertionError("NO REAL EXECUTION")):
            with self.assertRaisesRegex(ValueError, "STALE_PREPARED_BINDINGS"):
                e.verify_prepared(prepared, decision, implementation, bundle_pin)
            bundle = e.read(prepared / "bundle.json")
            self.assertNotEqual(bundle["runner_sha256"], implementation)
            identities = {}
            for label, manifest in bundle["manifests"].items():
                e.verify_snapshot(prepared / "snapshots" / label, manifest, identities=identities)
        self.assertEqual(set(bundle["manifests"]), {"B", "R", "N"})
        self.assertEqual(before, {p: p.read_bytes() for p in prepared.rglob("*") if p.is_file()})
        self.assertFalse((prepared / "authorization.json").exists())
        self.assertFalse((prepared / "execution-v1").exists())

    def test_real_active_gate_and_candidate_construction_are_read_only(self):
        before = {p: p.read_bytes() for p in REAL_LIVE.rglob("*") if p.is_file()}
        with patch.object(e.historical, "capture_process", side_effect=AssertionError("NO REAL EXECUTION")):
            active, trust = e.activation_gate(e.sha(e.raw(REAL_LIVE / e.activation.DECISION)), e.sha(e.raw(REAL_ROOT / "runner.py")))
            definition, sources, manifests = e.construction(trust)
        self.assertEqual(active["verified"]["trust_pins"]["check_sha256"], e.CHECK)
        self.assertEqual(definition["candidates"]["R"]["disclosure"], "INTENTIONALLY_SEEDED_REGRESSION")
        self.assertEqual(len(manifests["B"]["files"]), 43)
        self.assertNotEqual(sources["R"], sources["B"])
        self.assertFalse(any(n == "cachetools" or n.startswith("cachetools.") for n in sys.modules))
        self.assertEqual(before, {p: p.read_bytes() for p in REAL_LIVE.rglob("*") if p.is_file()})

    def test_real_gate_rejects_wrong_implementation_and_activation_pins(self):
        decision = e.sha(e.raw(REAL_LIVE / e.activation.DECISION)); implementation = e.sha(e.raw(REAL_ROOT / "runner.py"))
        for dec, impl in (("0" * 64, implementation), (decision, "0" * 64)):
            with self.assertRaisesRegex(ValueError, "CHANGED"):
                e.activation_gate(dec, impl)
            with patch("sys.stdout", io.StringIO()) as output:
                code = e.main(["preflight", "--runner-sha256", impl, "--activation-decision-sha256", dec])
            result = json.loads(output.getvalue()); assert_disclosure(self, result)
            self.assertEqual(code, 2); self.assertEqual(result["state"], "BLOCKED")

    def test_cli_bootstrap_failure_has_disclosure_and_preserves_failure_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            script = Path(temp).resolve() / "HINDSIGHT/product_mvp/checkpoint_e/runner.py"
            script.parent.mkdir(parents=True); shutil.copyfile(REAL_ROOT / "runner.py", script)
            # Missing trusted activation source: bootstrap fails before any imports/execution.
            result = subprocess.run([sys.executable, "-I", "-S", "-B", str(script), "preflight"],
                                    capture_output=True, check=False, timeout=10)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"MISSING_FILE", result.stderr)
            value = json.loads(result.stdout); assert_disclosure(self, value)
            self.assertEqual(value["state"], "BLOCKED")
            self.assertFalse(value["regression_detected"])

    def test_effective_activation_is_required_even_with_matching_decision_bytes(self):
        decision = e.sha(e.raw(REAL_LIVE / e.activation.DECISION)); implementation = e.sha(e.raw(REAL_ROOT / "runner.py"))
        with patch.object(e.activation, "validate_decision", return_value={"active": False}), self.assertRaisesRegex(ValueError, "EFFECTIVE_ACTIVE_REQUIRED"):
            e.activation_gate(decision, implementation)

    def test_real_collector_toy_timeout_and_output_bounds(self):
        # These are synthetic toy commands, never the approved check/candidates.
        with tempfile.TemporaryDirectory() as cwd:
            timeout = e.historical.capture_process([sys.executable, "-I", "-S", "-B", "-c", "while True: pass"], cwd, 0.15, 128, 128)
            self.assertEqual(timeout["transport"], "TIMEOUT")
            overflow = e.historical.capture_process([sys.executable, "-I", "-S", "-B", "-c", "print('x'*10000)"], cwd, 2, 128, 128)
            self.assertEqual(overflow["transport"], "OUTPUT_LIMIT")
            self.assertEqual(len(overflow["stdout"]), 128)

    def test_real_collector_sanitizes_environment_and_spawn_error(self):
        with tempfile.TemporaryDirectory() as cwd, patch.dict(os.environ, {"HINDSIGHT_TEST_SECRET": "never inherit"}):
            result = e.historical.capture_process([sys.executable, "-I", "-S", "-B", "-c", "import os; print('HINDSIGHT_TEST_SECRET' in os.environ)"], cwd, 2, 128, 128)
            self.assertEqual(result["stdout"], b"False\n")
            with patch.object(e.historical.subprocess, "Popen", side_effect=OSError("synthetic spawn failure")), self.assertRaises(OSError):
                e.historical.capture_process(["NEVER_SPAWN"], cwd, 2, 128, 128)


if __name__ == "__main__":
    unittest.main()
