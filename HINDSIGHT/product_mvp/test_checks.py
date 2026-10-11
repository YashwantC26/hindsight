"""Checkpoint C tests with synthetic cache doubles only; no historical check execution."""
import ast
from pathlib import Path
import unittest
from unittest.mock import patch

from checks import claim_mapping, conformance, decide_check, emit, generate_check
from common import HERE, canonical, sha
from semantics import contract_draft, recipe_draft


class SyntheticCache:
    """TEST_ONLY public mapping double; no cachetools or historical implementation."""
    events = []

    def __init__(self, maxsize, timer, ttu):
        self.data = {}
        self.timer, self.ttu = timer, ttu
        self.events.append("construct")

    def __setitem__(self, key, value):
        self.events.append(("set", key, value))
        if self.ttu(key, value, self.timer()) <= self.timer():
            self.data.pop(key, None)
        else:
            self.data[key] = value

    def __contains__(self, key):
        self.events.append(("contains", key))
        return key in self.data

    def __getitem__(self, key):
        self.events.append(("get", key))
        return self.data[key]


class TemplateTests(unittest.TestCase):
    def setUp(self):
        self.contract = contract_draft("e" * 64)
        self.recipe = recipe_draft()
        self.hashes = {"evidence_sha256": "e" * 64, "contract_sha256": sha(canonical(self.contract)),
                       "recipe_sha256": sha(canonical(self.recipe))}
        self.data = emit(self.contract, self.recipe, self.hashes)
        self.namespace = {"__name__": "TEST_ONLY_SYNTHETIC_MODULE"}
        exec(compile(self.data, "TEST_ONLY_generated_check.py", "exec"), self.namespace)
        SyntheticCache.events = []

    def test_regeneration_and_real_ast_assertion_chains(self):
        self.assertEqual(self.data, emit(self.contract, self.recipe, self.hashes))
        mapping = claim_mapping(self.data, self.contract, self.recipe)
        self.assertEqual(len(mapping["mappings"]), 12)
        self.assertEqual({r["claim_id"] for r in mapping["mappings"]}, {"C1", "C2", "C3", "C4"})
        for row in mapping["mappings"]:
            self.assertLess(row["operation"]["start_line"], row["observation"]["start_line"])
            self.assertLess(row["observation"]["start_line"], row["assertion"]["start_line"])

    def test_synthetic_pass_independent_scenarios_and_observation_order(self):
        result = self.namespace["run_checks"](SyntheticCache)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["scenarios"]), 4)
        self.assertEqual(sum(len(s["assertions"]) for s in result["scenarios"]), 12)
        self.assertEqual(SyntheticCache.events.count("construct"), 4)
        events = SyntheticCache.events
        for value in (0, -1, 3):
            action = events.index(("set", 1, value))
            self.assertEqual(events[action + 1:action + 4], [("contains", 1), ("get", 1), ("get", 2)])

    def test_synthetic_stale_value_is_designated_failure_and_does_not_abort(self):
        class StaleValue(SyntheticCache):
            def __setitem__(self, key, value):
                if value <= 0:
                    return
                super().__setitem__(key, value)
        result = self.namespace["run_checks"](StaleValue)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual([s["status"] for s in result["scenarios"]], ["FAIL", "FAIL", "PASS", "PASS"])
        for scenario in result["scenarios"][:2]:
            self.assertEqual([r["claim_id"] for r in scenario["assertions"] if r["status"] == "FAIL"], ["C1", "C2"])

    def test_constructor_and_library_assertion_errors_never_count_as_detection(self):
        class ConstructorError:
            def __init__(self, **kwargs):
                raise AttributeError("TEST_ONLY API error")
        class AssignmentError(SyntheticCache):
            def __setitem__(self, key, value):
                if value <= 0:
                    raise AssertionError("TEST_ONLY library assertion")
                super().__setitem__(key, value)
        for cls in (ConstructorError, AssignmentError):
            result = self.namespace["run_checks"](cls)
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(len(result["scenarios"]), 4)
            self.assertFalse(any(r["status"] == "FAIL" for s in result["scenarios"] for r in s["assertions"]))

    def test_missing_survivor_is_claim_failure_but_unexpected_exception_is_error(self):
        class LostSurvivor(SyntheticCache):
            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if value <= 0:
                    self.data.pop(2, None)
        result = self.namespace["run_checks"](LostSurvivor)
        self.assertEqual(result["status"], "FAIL")
        failures = [r for s in result["scenarios"] for r in s["assertions"] if r["status"] == "FAIL"]
        self.assertEqual({r["claim_id"] for r in failures}, {"C3"})
        class LookupError(LostSurvivor):
            def __getitem__(self, key):
                if key not in self.data:
                    raise AssertionError("TEST_ONLY lookup runtime error")
                return super().__getitem__(key)
        self.assertEqual(self.namespace["run_checks"](LookupError)["status"], "ERROR")

    def test_tampered_check_rejected_before_static_api_checks(self):
        modified = self.data.replace(b'"target_absent", membership', b'"target_absent", target_read')
        with self.assertRaisesRegex(ValueError, "BYTE_MISMATCH"):
            conformance(Path("/unused"), modified, self.contract, self.recipe, self.hashes)
        missing = ast.parse(self.data)
        self.assertTrue(missing.body)
        altered = self.data.replace(b'record_assertion(records, "C2", "target_lookup_KeyError", target_read, {"kind": "KeyError"})', b'pass')
        with self.assertRaisesRegex(ValueError, "C1_C4_ASSERTION_COVERAGE"):
            claim_mapping(altered, self.contract, self.recipe)


    def test_missing_semantic_approval_blocks_before_emission(self):
        with patch("checks.require_semantic_approval", side_effect=ValueError("REAL_SEMANTIC_APPROVAL_REQUIRED")), patch("checks.emit") as emitter:
            with self.assertRaises(ValueError):
                generate_check(Path("/unused"))
            emitter.assert_not_called()

    def test_no_implicit_or_stale_check_approval_writes(self):
        with self.assertRaisesRegex(ValueError, "explicit developer"):
            decide_check(Path("/unused"), decision="approve", reviewer="TEST_ONLY", review_minutes=1,
                         note="TEST_ONLY", expected_hashes={}, confirmed=False)
        with patch("checks.verify_check", return_value={"check_sha256": "current"}), patch("checks.write") as writer:
            with self.assertRaisesRegex(ValueError, "CHECK_REVIEW_HASH_MISMATCH"):
                decide_check(Path("/unused"), decision="approve", reviewer="TEST_ONLY", review_minutes=1,
                             note="TEST_ONLY negative test", expected_hashes={"check_sha256": "stale"}, confirmed=True)
            writer.assert_not_called()


if __name__ == "__main__":
    unittest.main()
