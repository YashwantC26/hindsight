"""One finite normative record; no general behavioral language or generator."""
import math

from common import canonical

ORIGINS = {"operator_proposed", "developer_supplied", "developer_corrected", "upstream_reference", "model_proposed"}
PREDICATES = {
    "C1": "expired_assignment_target_membership_is_false",
    "C2": "expired_assignment_target_lookup_raises_KeyError",
    "C3": "live_survivor_lookup_equals_initial_value",
    "C4": "positive_expiry_replacement_is_present_and_readable_as_new_value",
}
PRECONDITIONS = ["constant_clock", "target_live_before_overwrite", "incoming_expiry_not_after_now",
                 "independently_live_survivor", "finite_integer_fixture"]
ALL_SCENARIOS = ["expiry_at_boundary", "expiry_before_boundary", "valid_replacement", "absent_target"]
EXPIRED_SCENARIOS = ["expiry_at_boundary", "expiry_before_boundary", "absent_target"]
CLAIM_SCENARIOS = {"C1": EXPIRED_SCENARIOS, "C2": EXPIRED_SCENARIOS, "C3": ALL_SCENARIOS,
                   "C4": ["valid_replacement"]}
PRECONDITION_SCENARIOS = {kind: ALL_SCENARIOS for kind in PRECONDITIONS}
PRECONDITION_SCENARIOS["target_live_before_overwrite"] = ALL_SCENARIOS[:3]
PRECONDITION_SCENARIOS["incoming_expiry_not_after_now"] = EXPIRED_SCENARIOS
EXCLUSIONS = ["physical_heap_cleanup", "assignment_return_value", "concurrency", "effectful_callbacks",
              "arbitrary_values", "capacity_eviction", "universal_expiry_schedules"]


def contract_draft(evidence_sha256):
    text = {
        "C1": "After assigning an expired incoming replacement, the target key is absent from membership.",
        "C2": "After assigning an expired incoming replacement, direct target lookup raises KeyError.",
        "C3": "The independently live survivor remains readable with its original value.",
        "C4": "A replacement with expiry after the fixed current time is present and reads as the new value.",
    }
    return {"schema_version": 1, "contract_id": "cachetools-tlru-expired-replacement", "version": 1,
            "evidence_sha256": evidence_sha256, "subject": "cachetools.TLRUCache.__setitem__",
            "normative_form": "finite_predicates_and_precondition_kinds; display_text_is_explanatory",
            "semantics_origin": "operator_proposed", "upstream_reference_exposure": True,
            "preconditions": [{"id": "P" + str(i), "kind": kind, "origin": "operator_proposed",
                               "scenario_ids": PRECONDITION_SCENARIOS[kind].copy()}
                              for i, kind in enumerate(PRECONDITIONS, 1)],
            "claims": [{"id": identity, "predicate": predicate, "display_text": text[identity],
                        "origin": "operator_proposed", "essential": True,
                        "scenario_ids": CLAIM_SCENARIOS[identity].copy()}
                       for identity, predicate in PREDICATES.items()],
            "exclusions": EXCLUSIONS.copy(), "reviewer_notes": []}


def recipe_draft():
    return {"schema_version": 1, "template_id": "tlru_expired_replacement_v1",
            "origin": "operator_proposed", "clock_now": 10, "maxsize": 2,
            "target_key": 1, "old_value": 5, "survivor_key": 2, "survivor_value": 7,
            "clock_kind": "constant_integer", "ttu_kind": "now_plus_incoming_value",
            "scenarios": [
                {"id": "expiry_at_boundary", "initial_target_present": True, "replacement": 0,
                 "expected_target": "absent", "claim_ids": ["C1", "C2", "C3"], "historical_role": "discriminator"},
                {"id": "expiry_before_boundary", "initial_target_present": True, "replacement": -1,
                 "expected_target": "absent", "claim_ids": ["C1", "C2", "C3"], "historical_role": "discriminator"},
                {"id": "valid_replacement", "initial_target_present": True, "replacement": 3,
                 "expected_target": "new_value", "claim_ids": ["C3", "C4"], "historical_role": "control"},
                {"id": "absent_target", "initial_target_present": False, "replacement": 0,
                 "expected_target": "absent", "claim_ids": ["C1", "C2", "C3"], "historical_role": "control"},
            ], "reviewer_notes": []}


def validate_semantics(contract, recipe, evidence_sha256):
    """Reject unsupported normative edits; never silently reinterpret or repair them."""
    expected_contract = contract_draft(evidence_sha256)
    expected_recipe = recipe_draft()
    if type(contract) is not dict or set(contract) != set(expected_contract):
        raise ValueError("UNSUPPORTED_CONTRACT_FIELDS")
    if type(recipe) is not dict or set(recipe) != set(expected_recipe):
        raise ValueError("UNSUPPORTED_RECIPE_FIELDS")
    for name in ("schema_version", "version"):
        if type(contract[name]) is not int:
            raise ValueError("CONTRACT_VERSION_TYPE")
    for key in ("schema_version", "clock_now", "maxsize", "target_key", "old_value", "survivor_key", "survivor_value"):
        if type(recipe[key]) is not int:
            raise ValueError("RECIPE_INTEGER_REQUIRED: " + key)
    # The attempt fixes the exact MVP scenarios; this is not a DSL for arbitrary edits.
    for key, value in expected_recipe.items():
        if key not in ("origin", "reviewer_notes") and canonical(recipe[key]) != canonical(value):
            raise ValueError("UNSUPPORTED_RECIPE_CHANGE: " + key)
    if type(recipe["scenarios"]) is not list:
        raise ValueError("SCENARIO_LIST_REQUIRED")
    for scenario in recipe["scenarios"]:
        if type(scenario["initial_target_present"]) is not bool or type(scenario["replacement"]) is not int:
            raise ValueError("SCENARIO_TYPES")
    for key, value in expected_contract.items():
        if key not in ("semantics_origin", "preconditions", "claims", "reviewer_notes") and canonical(contract[key]) != canonical(value):
            raise ValueError("UNSUPPORTED_CONTRACT_CHANGE: " + key)
    if contract["semantics_origin"] not in ORIGINS or recipe["origin"] not in ORIGINS:
        raise ValueError("SEMANTIC_ORIGIN_REQUIRED")
    if type(contract["claims"]) is not list or len(contract["claims"]) != 4:
        raise ValueError("EXACT_C1_C4_REQUIRED")
    for actual, expected in zip(contract["claims"], expected_contract["claims"]):
        if type(actual) is not dict or set(actual) != set(expected):
            raise ValueError("CLAIM_FIELDS")
        if any(canonical(actual[k]) != canonical(expected[k]) for k in ("id", "predicate", "scenario_ids")) or actual["essential"] is not True:
            raise ValueError("UNSUPPORTED_NORMATIVE_CLAIM")
        if actual["origin"] not in ORIGINS or not isinstance(actual["display_text"], str) or not actual["display_text"].strip():
            raise ValueError("CLAIM_EXPLANATION_OR_ORIGIN")
    if type(contract["preconditions"]) is not list or len(contract["preconditions"]) != len(PRECONDITIONS):
        raise ValueError("EXACT_PRECONDITIONS_REQUIRED")
    for actual, expected in zip(contract["preconditions"], expected_contract["preconditions"]):
        if (type(actual) is not dict or set(actual) != set(expected)
                or any(canonical(actual[k]) != canonical(expected[k]) for k in ("id", "kind", "scenario_ids")) or actual["origin"] not in ORIGINS):
            raise ValueError("UNSUPPORTED_PRECONDITION")
    for scenario in recipe["scenarios"]:
        computed = [c["id"] for c in contract["claims"] if scenario["id"] in c["scenario_ids"]]
        if computed != scenario["claim_ids"]:
            raise ValueError("CLAIM_SCENARIO_COVERAGE_MISMATCH")
    for artifact in (contract, recipe):
        if type(artifact["reviewer_notes"]) is not list or not all(type(v) is str for v in artifact["reviewer_notes"]):
            raise ValueError("REVIEW_NOTES_MUST_BE_STRINGS")


def corrections(before, after, path=""):
    if type(before) is dict and type(after) is dict:
        return [item for key in sorted(before.keys() | after.keys())
                for item in corrections(before.get(key), after.get(key), path + "/" + key)]
    if type(before) is list and type(after) is list and len(before) == len(after):
        return [item for i, (a, b) in enumerate(zip(before, after)) for item in corrections(a, b, path + "/" + str(i))]
    return [] if type(before) is type(after) and before == after else [{"path": path, "before": before, "after": after,
                                                                     "origin": "developer_edited"}]


def validate_review_metadata(reviewer, review_minutes, note):
    if not reviewer.strip() or not note.strip():
        raise ValueError("Reviewer identity and explicit authorization note are required")
    if not math.isfinite(review_minutes) or review_minutes < 0:
        raise ValueError("Review minutes must be finite, nonnegative, and developer-reported")
