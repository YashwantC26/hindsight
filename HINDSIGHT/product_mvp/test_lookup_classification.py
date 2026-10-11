"""Focused corrective-template tests. Synthetic mappings only; never historical A/B."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from checks import artifact_paths, current_version, emit, verify_check
import test_checks as template_fixtures

SyntheticCache = template_fixtures.SyntheticCache


class EqualInt(int):
    pass


class OpaqueValue:
    def __repr__(self):
        raise AssertionError("Diagnostic repr must never execute")

    def __str__(self):
        raise AssertionError("Diagnostic str must never execute")

    def __eq__(self, other):
        return False


class EqualityRaises(OpaqueValue):
    def __eq__(self, other):
        raise ValueError("TEST_ONLY equality failure")


class EqualObject(OpaqueValue):
    def __eq__(self, other):
        return other == 7


class AmbiguousTruth:
    def __bool__(self):
        raise ValueError("TEST_ONLY ambiguous truth")


class AmbiguousEquality(OpaqueValue):
    def __eq__(self, other):
        return AmbiguousTruth()


class UnformattableException(Exception):
    def __str__(self):
        raise AssertionError("Exception str must never execute")


def classification_matrix(namespace):
    """Run the production observer/classifier on synthetic lookup-only mappings."""
    cases = [
        ("C2_expected_KeyError", "C2", KeyError(), True, "PASS"),
        ("C2_success_integer", "C2", 5, False, "FAIL"),
        ("C2_success_string", "C2", "wrong", False, "FAIL"),
        ("C2_success_custom_object", "C2", OpaqueValue(), False, "FAIL"),
        ("C3_correct_survivor", "C3", 7, False, "PASS"),
        ("C3_incorrect_integer", "C3", 8, False, "FAIL"),
        ("C3_incorrect_string", "C3", "wrong", False, "FAIL"),
        ("C3_equal_integer_subclass", "C3", EqualInt(7), False, "PASS"),
        ("C3_equal_custom_object", "C3", EqualObject(), False, "PASS"),
        ("C4_equal_integer_subclass", "C4", EqualInt(3), False, "PASS"),
        ("C4_incorrect_string", "C4", "wrong", False, "FAIL"),
        ("C2_unexpected_lookup_exception", "C2", UnformattableException(), True, "ERROR"),
        ("C3_equality_raises", "C3", EqualityRaises(), False, "ERROR"),
        ("C3_ambiguous_equality", "C3", AmbiguousEquality(), False, "ERROR"),
        ("C3_custom_object_unequal", "C3", OpaqueValue(), False, "FAIL"),
    ]
    results = []
    for name, claim, value, raises, expected_status in cases:
        class LookupOnly:
            def __getitem__(self, key):
                if raises:
                    raise value
                return value
        observed = namespace["observe_lookup"](LookupOnly(), 1)
        expected = {"kind": "KeyError"} if claim == "C2" else {"kind": "value", "value": 7 if claim == "C3" else 3}
        records = []
        namespace["record_assertion"](records, claim, "TEST_ONLY", observed, expected)
        record = records[0]
        encoded = json.dumps(record, allow_nan=False, sort_keys=True)
        results.append({"case": name, "expected_status": expected_status,
                        "actual_status": record["status"], "passed": record["status"] == expected_status,
                        "json_serialization": "PASS", "record": json.loads(encoded)})
    return results


class LookupClassification(unittest.TestCase):
    def setUp(self):
        template_fixtures.TemplateTests.setUp(self)

    def test_required_lookup_classification_matrix(self):
        for row in classification_matrix(self.namespace):
            with self.subTest(case=row["case"]):
                self.assertTrue(row["passed"])

    def test_c2_does_not_evaluate_successful_return_equality(self):
        class NoEquality(OpaqueValue):
            def __eq__(self, other):
                raise AssertionError("C2 must never evaluate successful-return equality")
        records = []
        self.namespace["record_assertion"](records, "C2", "TEST_ONLY", {"kind": "value", "value": NoEquality()}, {"kind": "KeyError"})
        self.assertEqual(records[0]["status"], "FAIL")
        json.dumps(records, allow_nan=False)

    def test_equal_integer_subclass_satisfies_setup_and_all_claims(self):
        class EqualValues(SyntheticCache):
            def __getitem__(self, key):
                return EqualInt(super().__getitem__(key))
        result = self.namespace["run_checks"](EqualValues)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(sum(len(s["assertions"]) for s in result["scenarios"]), 12)
        json.dumps(result, allow_nan=False)

    def test_setup_mismatch_is_error_without_behavioral_assertions(self):
        class IncorrectSetup(SyntheticCache):
            def __getitem__(self, key):
                return 999
        result = self.namespace["run_checks"](IncorrectSetup)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(len(result["scenarios"]), 4)
        self.assertTrue(all(s["error"]["stage"] == "setup" and not s["assertions"] for s in result["scenarios"]))

    def test_independent_assertions_and_scenarios_survive_failures_and_evaluation_errors(self):
        class MixedOutcomes(SyntheticCache):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                self.acted = False

            def __setitem__(self, key, value):
                super().__setitem__(key, value)
                if key == 1 and value <= 0:
                    self.acted = True

            def __getitem__(self, key):
                if self.acted:
                    return OpaqueValue() if key == 1 else EqualityRaises()
                return super().__getitem__(key)
        result = self.namespace["run_checks"](MixedOutcomes)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(sum(len(s["assertions"]) for s in result["scenarios"]), 12)
        self.assertEqual([(r["claim_id"], r["status"]) for r in result["scenarios"][0]["assertions"]],
                         [("C1", "PASS"), ("C2", "FAIL"), ("C3", "ERROR")])
        self.assertEqual(result["scenarios"][0]["assertions"][2]["error_stage"], "equality_evaluation")
        self.assertEqual(result["scenarios"][2]["status"], "PASS")
        json.dumps(result, allow_nan=False)

    def test_diagnostics_are_bounded_and_never_traverse_or_format_objects(self):
        cycle = []
        cycle.append(cycle)
        for value in (OpaqueValue(), cycle, b"bytes", "x" * 10000, 1 << 10000, float("inf"), float("nan")):
            diagnostic = self.namespace["diagnostic_value"](value)
            encoded = json.dumps(diagnostic, allow_nan=False)
            self.assertLess(len(encoded), 300)
        # Diagnostic normalization must not determine equality: 7.0 == 7 is true.
        records = []
        self.namespace["record_assertion"](records, "C3", "TEST_ONLY", {"kind": "value", "value": 7.0}, {"kind": "value", "value": 7})
        self.assertEqual(records[0]["status"], "PASS")

    def test_unexpected_exception_diagnostics_do_not_call_exception_str(self):
        class BadSetup:
            def __init__(self, **kwargs):
                raise UnformattableException()
        result = self.namespace["run_checks"](BadSetup)
        self.assertEqual(result["status"], "ERROR")
        self.assertEqual(len(result["scenarios"]), 4)
        json.dumps(result, allow_nan=False)

    def test_version_selection_blocks_fallback_and_preserves_old_emission(self):
        original = emit(self.contract, self.recipe, self.hashes, version=1)
        self.assertIn(b"UnexpectedValueType", original)
        self.assertNotIn(b"UnexpectedValueType", self.data)
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            self.assertEqual(current_version(run), 1)
            (run / "generated-v2").mkdir()
            self.assertEqual(current_version(run), 2)
            with patch("checks.require_semantic_approval", return_value={"hashes": self.hashes}):
                with self.assertRaises(FileNotFoundError):
                    verify_check(run)
            self.assertEqual(artifact_paths(run, 2)[2].name, "check-decision.v2.json")


if __name__ == "__main__":
    unittest.main()
