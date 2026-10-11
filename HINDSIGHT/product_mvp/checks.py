"""Finite template emission and exact-byte Checkpoint C review. Never executes history."""
import ast
import inspect
from pathlib import Path

from common import HERE, PRODUCTION, now, read, sha, write, write_bytes
from review import require_semantic_approval
from semantics import CLAIM_SCENARIOS, validate_review_metadata, validate_semantics

TEMPLATES = {1: HERE / "templates/tlru_expired_replacement_v1.py.tmpl",
             2: HERE / "templates/tlru_expired_replacement_v1.r2.py.tmpl"}
TEMPLATE = TEMPLATES[2]
ASSERTIONS = {"C1": ["target_absent"], "C2": ["target_lookup_KeyError"],
              "C3": ["survivor_unchanged"], "C4": ["target_present", "target_reads_replacement"]}


def artifact_paths(run, version):
    if type(version) is not int or version not in TEMPLATES:
        raise ValueError("UNSUPPORTED_GENERATION_VERSION")
    return (run / ("generated" if version == 1 else "generated-v2"),
            run / ("checkpoint-c.json" if version == 1 else "checkpoint-c.v2.json"),
            run / ("check-decision.json" if version == 1 else "check-decision.v2.json"))


def current_version(run):
    # A partially written corrective version blocks fallback to the known-bad one.
    return 2 if (run / "checkpoint-c.v2.json").exists() or (run / "generated-v2").exists() else 1


def check_exists(run):
    generated, checkpoint, _ = artifact_paths(run, current_version(run))
    return generated.exists() or checkpoint.exists()


def emit(contract, recipe, hashes, version=2):
    validate_semantics(contract, recipe, hashes["evidence_sha256"])
    template = TEMPLATES[version].read_bytes()
    text = template.decode()
    substitutions = {"__CONTRACT_SHA256__": repr(hashes["contract_sha256"]),
                     "__RECIPE_SHA256__": repr(hashes["recipe_sha256"]),
                     "__TEMPLATE_SHA256__": repr(sha(template)), "__RECIPE__": repr(recipe)}
    for marker, replacement in substitutions.items():
        if text.count(marker) != 1:
            raise ValueError("TEMPLATE_MARKER_MISMATCH: " + marker)
        text = text.replace(marker, replacement)
    return text.encode()


def source_span(source, node):
    return {"start_line": node.lineno, "end_line": node.end_lineno,
            "source": ast.get_source_segment(source, node)}


def claim_mapping(data, contract, recipe):
    """Locate actual construction/action/observation/assertion AST nodes, then join scopes."""
    source = data.decode()
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    run = functions["run_checks"]
    calls = [node for node in ast.walk(run) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    constructor = next(node for node in calls if node.func.id == "cache_class")
    if [kw.arg for kw in constructor.keywords] != ["maxsize", "timer", "ttu"]:
        raise ValueError("CONSTRUCTOR_KEYWORDS_MISMATCH")
    action = [node for node in ast.walk(run) if isinstance(node, ast.Assign)
              and ast.unparse(node) == "cache[target] = scenario['replacement']"]
    if len(action) != 1:
        raise ValueError("EXACT_ASSIGNMENT_REQUIRED")
    observations = {}
    for node in ast.walk(run):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("membership", "target_read", "survivor_read"):
                observations[node.targets[0].id] = node
    expected_observations = {"membership": "observe_membership(cache, target)",
                             "target_read": "observe_lookup(cache, target)",
                             "survivor_read": "observe_lookup(cache, survivor)"}
    if set(observations) != set(expected_observations) or any(
            ast.unparse(observations[k].value) != v for k, v in expected_observations.items()):
        raise ValueError("OBSERVATION_CHAIN_MISMATCH")
    if not action[0].lineno < observations["membership"].lineno < observations["target_read"].lineno < observations["survivor_read"].lineno:
        raise ValueError("OBSERVATION_ORDER_MISMATCH")
    records = {}
    for node in calls:
        if node.func.id != "record_assertion":
            continue
        claim, identity = ast.literal_eval(node.args[1]), ast.literal_eval(node.args[2])
        if (claim, identity) in records:
            raise ValueError("DUPLICATE_ASSERTION")
        observed_name = node.args[3].id
        if observed_name not in observations or node.lineno <= observations[observed_name].lineno:
            raise ValueError("ASSERTION_WITHOUT_OBSERVATION")
        records[(claim, identity)] = {"claim_id": claim, "assertion_id": identity,
                                    "observation_name": observed_name,
                                    "observation": source_span(source, observations[observed_name]),
                                    "observation_helper": source_span(source, functions[
                                        "observe_membership" if observed_name == "membership" else "observe_lookup"]),
                                    "assertion": source_span(source, node),
                                    "expected_expression": ast.unparse(node.args[4])}
    expected = {(claim, identity) for claim, identities in ASSERTIONS.items() for identity in identities}
    if set(records) != expected:
        raise ValueError("C1_C4_ASSERTION_COVERAGE_MISMATCH")
    mappings = []
    for claim in contract["claims"]:
        if claim["scenario_ids"] != CLAIM_SCENARIOS[claim["id"]]:
            raise ValueError("CLAIM_SCOPE_CHANGED")
        for scenario in recipe["scenarios"]:
            if scenario["id"] not in claim["scenario_ids"]:
                continue
            for identity in ASSERTIONS[claim["id"]]:
                mappings.append({"scenario_id": scenario["id"], "predicate": claim["predicate"],
                                 "constructor": source_span(source, constructor),
                                 "operation": source_span(source, action[0]), **records[(claim["id"], identity)]})
    result = {"check_sha256": sha(data), "method": "AST-located finite operation/observation/assertion chains; scopes checked against approved records",
            "runtime_branch_conformance": "exact regenerated bytes and AST; no general data-flow proof",
            "assertion_classifier": source_span(source, functions["record_assertion"]), "mappings": mappings}
    if "evaluate_observation" in functions:
        result["equality_evaluator"] = source_span(source, functions["evaluate_observation"])
        result["diagnostic_conversion"] = source_span(source, functions["diagnostic_value"])
    return result


def api_checks(run):
    results = {}
    for label in ("A", "B"):
        data = (run / "snapshots" / label / PRODUCTION).read_bytes()
        source = data.decode()
        tree = ast.parse(source)
        classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
        cls = classes["TLRUCache"]
        methods = {node.name: node for node in cls.body if isinstance(node, ast.FunctionDef)}
        init = methods["__init__"]
        positional = init.args.posonlyargs + init.args.args
        parameters = [inspect.Parameter(n.arg, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                      default=inspect.Parameter.empty if i < len(positional) - len(init.args.defaults) else None)
                      for i, n in enumerate(positional)]
        inspect.Signature(parameters).bind(object(), maxsize=2, ttu=object(), timer=object())
        for method, count in (("__contains__", 2), ("__getitem__", 2), ("__setitem__", 3)):
            node = methods[method]
            args = node.args.posonlyargs + node.args.args
            if not len(args) - len(node.args.defaults) <= count <= len(args):
                raise ValueError("MAPPING_API_ARITY_MISMATCH: " + method)
        ttu = methods["ttu"]
        if not any(ast.unparse(n) == "property" for n in ttu.decorator_list):
            raise ValueError("TTU_PROPERTY_DIAGNOSTIC_CHANGED")
        callback_calls = [node for node in ast.walk(methods["__setitem__"])
                          if isinstance(node, ast.Call) and ast.unparse(node.func) == "self.__ttu"]
        if len(callback_calls) != 1 or len(callback_calls[0].args) != 3:
            raise ValueError("TTU_CALLBACK_ARITY_MISMATCH")
        results[label] = {"status": "PASS_STATIC", "source_sha256": sha(data),
                          "constructor": source_span(source, init),
                          "mapping_methods": {name: source_span(source, methods[name]) for name in ("__contains__", "__getitem__", "__setitem__")},
                          "ttu_is_property": True, "callback_supplied_in_constructor": True,
                          "ttu_invocation": source_span(source, callback_calls[0]),
                          "ttu_callback_arity": 3, "clock_callback_arity": 0,
                          "limit": "Local AST signatures/definitions only; runtime compatibility NOT_RUN"}
    return results


def conformance(run, data, contract, recipe, hashes, version=2):
    regenerated = emit(contract, recipe, hashes, version)
    if data != regenerated:
        raise ValueError("GENERATED_CHECK_BYTE_MISMATCH")
    tree = ast.parse(data)
    if ast.dump(tree, include_attributes=False) != ast.dump(ast.parse(regenerated), include_attributes=False):
        raise ValueError("GENERATED_CHECK_AST_MISMATCH")
    compile(tree, "generated_check.py", "exec", dont_inherit=True)  # compile only; no execution
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    if len(functions["time_to_use"].args.args) != 3 or functions["constant_clock"].args.args:
        raise ValueError("GENERATED_CALLBACK_ARITY_MISMATCH")
    diagnostic_lengths = {id(node) for node in ast.walk(functions["diagnostic_value"])
                          if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "len"} if version == 2 else set()
    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "cache":
            forbidden.append(ast.unparse(node))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec", "len", "iter", "setattr", "getattr") and id(node) not in diagnostic_lengths:
            forbidden.append(ast.unparse(node))
    if forbidden:
        raise ValueError("FORBIDDEN_CHECK_OPERATION: " + repr(forbidden))
    mapping = claim_mapping(data, contract, recipe)
    return {"status": "PASS_STATIC", "byte_regeneration": "PASS", "ast_regeneration": "PASS",
            "python_compilation": "PASS_NO_EXECUTION", "forbidden_operations": [],
            "scenario_count": len(recipe["scenarios"]), "scoped_assertion_count": len(mapping["mappings"]),
            "claim_ids": [claim["id"] for claim in contract["claims"]],
            "api_checks": api_checks(run), "behavioral_support": "HUMAN_APPROVED, NOT_MECHANICALLY_PROVED",
            "runtime_generated_check_execution": "NOT_RUN", "historical_product_validation": "NOT_RUN"}


def generate_check(run):
    decision = require_semantic_approval(run)
    version = 2
    generated, checkpoint_path, _ = artifact_paths(run, version)
    if checkpoint_path.exists() or generated.exists():
        raise ValueError("Generated artifacts already exist; never repair or overwrite an attempt")
    previous = verify_check(run, 1) if (run / "checkpoint-c.json").exists() else None
    if previous and (run / "check-decision.json").exists():
        raise ValueError("A decided original check needs a separately authorized lifecycle change")
    hashes = decision["hashes"]
    contract, recipe = (read(run / "semantic-reviewed" / (name + ".json")) for name in ("contract", "recipe"))
    data = emit(contract, recipe, hashes)
    mapping = claim_mapping(data, contract, recipe)
    validation = conformance(run, data, contract, recipe, hashes)
    write_bytes(generated / "check.py", data)
    write(generated / "claim-map.json", mapping)
    write(generated / "conformance.json", validation)
    packet = render_packet(data, decision, mapping, validation)
    write_bytes(generated / "REVIEW_PACKET.md", packet.encode())
    paths = [run / "semantic-decision.json"] + [generated / name for name in ("check.py", "claim-map.json", "conformance.json", "REVIEW_PACKET.md")]
    files = {p.relative_to(run).as_posix(): sha(p.read_bytes()) for p in paths}
    record = {"created_at": now(), "checkpoint": "C", "state": "AWAITING_CHECK_APPROVAL", **hashes,
              "template_sha256": sha(TEMPLATE.read_bytes()), "files": files,
              "check_sha256": sha(data), "historical_product_validation": "NOT_RUN", "active": False}
    record["generation_version"] = version
    record["supersedes"] = previous
    write(checkpoint_path, record)
    return check_status(run)


def verify_check(run, version=None):
    decision = require_semantic_approval(run)
    version = current_version(run) if version is None else version
    generated, checkpoint_path, _ = artifact_paths(run, version)
    checkpoint = read(checkpoint_path)
    if version == 2:
        if checkpoint["generation_version"] != 2:
            raise ValueError("GENERATION_VERSION_MISMATCH")
        if checkpoint["supersedes"] is not None and checkpoint["supersedes"] != verify_check(run, 1):
            raise ValueError("ORIGINAL_CHECK_VERSION_CHANGED")
    if any(checkpoint[k] != v for k, v in decision["hashes"].items()):
        raise ValueError("CHECK_SEMANTIC_BINDING_MISMATCH")
    if checkpoint["template_sha256"] != sha(TEMPLATES[version].read_bytes()):
        raise ValueError("TEMPLATE_CHANGED")
    expected_files = {"semantic-decision.json"} | {(generated / name).relative_to(run).as_posix()
                       for name in ("check.py", "claim-map.json", "conformance.json", "REVIEW_PACKET.md")}
    if set(checkpoint["files"]) != expected_files:
        raise ValueError("CHECKPOINT_FILE_SET_MISMATCH")
    for name, expected in checkpoint["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts or (run / name).is_symlink() or sha((run / name).read_bytes()) != expected:
            raise ValueError("CHECK_REVIEW_ARTIFACT_CHANGED: " + name)
    contract, recipe = (read(run / "semantic-reviewed" / (name + ".json")) for name in ("contract", "recipe"))
    data = (generated / "check.py").read_bytes()
    if checkpoint["check_sha256"] != sha(data):
        raise ValueError("CHECK_HASH_MISMATCH")
    if claim_mapping(data, contract, recipe) != read(generated / "claim-map.json"):
        raise ValueError("CHECK_MAPPING_MISMATCH")
    if conformance(run, data, contract, recipe, decision["hashes"], version) != read(generated / "conformance.json"):
        raise ValueError("CHECK_CONFORMANCE_MISMATCH")
    return {"checkpoint_sha256": sha(checkpoint_path.read_bytes()), "check_sha256": sha(data)}


def check_status(run):
    hashes = verify_check(run)
    version = current_version(run)
    generated, _, path = artifact_paths(run, version)
    state = "AWAITING_CHECK_APPROVAL"
    if path.exists():
        decision = read(path)
        state = "CHECK_APPROVED" if decision["decision"] == "approve" else "CHECK_REJECTED"
        if decision["hashes"] != hashes:
            state = "INVALIDATED"
    return {"checkpoint": "C", "state": state, **hashes, "generation_version": version,
            "review_packet": (generated / "REVIEW_PACKET.md").relative_to(run).as_posix(), "product_check_generated": True,
            "historical_product_validation": "NOT_RUN", "active": False}


def decide_check(run, *, decision, reviewer, review_minutes, note, expected_hashes, confirmed):
    if not confirmed:
        raise ValueError("An explicit developer confirmation flag is required; never auto-approve")
    validate_review_metadata(reviewer, review_minutes, note)
    hashes = verify_check(run)
    if hashes != expected_hashes:
        raise ValueError("CHECK_REVIEW_HASH_MISMATCH")
    if decision not in ("approve", "reject"):
        raise ValueError("Unknown check decision")
    record = {"created_at": now(), "stage": "exact_generated_check_and_claim_mapping", "decision": decision,
              "reviewer": reviewer, "review_minutes": review_minutes, "authorization_note": note,
              "review_time_origin": "developer_reported_active_minutes; not inferred from elapsed time",
              "identity_assurance": "local explicit self-attestation; not strong authentication", "hashes": hashes}
    _, _, decision_path = artifact_paths(run, current_version(run))
    write(decision_path, record)
    return record


def render_packet(data, decision, mapping, validation):
    rows = ["# Checkpoint C: generated-check review", "", "**AWAITING EXPLICIT CHECK APPROVAL. Historical product validation NOT_RUN.**", "",
            "Corrective generation version 2. The original generated/ and checkpoint-c.json remain frozen and are superseded for review.",
            "The Checkpoint B draft packet is preserved as written; the separate semantic decision is now approved.",
            f"Semantic reviewer: {decision['reviewer']}; reported active review: {decision['review_minutes']} minutes.",
            "This is an operator/upstream-reference-assisted finite product attempt. No autonomous recovery or new coverage is claimed.", "",
            "## Exact artifacts", "", f"Check SHA-256: `{sha(data)}`", "",
            f"Template SHA-256: `{sha(TEMPLATE.read_bytes())}`", ""]
    rows += [f"{key}: `{value}`" for key, value in decision["hashes"].items()]
    rows += ["", "## Execution and observation order", "",
             "Four scenarios run in recipe order: expiry_at_boundary, expiry_before_boundary, valid_replacement, absent_target.",
             "Each creates a fresh maxsize=2 cache with clock=10 and constructor-supplied ttu(key,value,now)=now+value.",
             "Insert target=1/value=5 where present, then survivor=2/value=7. Confirm target membership and lookup, then survivor membership and lookup.",
             "Setup mismatch or constructor/assignment exception is ERROR; it produces no designated behavioral failure.",
             "Assign target the approved replacement (0, -1, 3, 0 respectively). Observe target membership, direct target lookup, then survivor lookup.",
             "Evaluate every applicable assertion independently; continue with later scenarios even after ERROR or FAIL.",
             "No len/currsize/iteration/cleanup/private-state observation, sleeps, callback reassignment, or monkeypatching is used.", "",
             "## Claim-to-assertion mapping", "",
             "Line numbers below refer to generated-v2/check.py. The complete AST-located chains and exact snippets are in claim-map.json.", "",
             "| Scenario | Claim | Assertion | Action line | Observation line | Assertion line | Expected expression |",
             "| --- | --- | --- | ---: | ---: | ---: | --- |"]
    rows += [f"| {r['scenario_id']} | {r['claim_id']} | {r['assertion_id']} | {r['operation']['start_line']} | {r['observation']['start_line']} | {r['assertion']['start_line']} | `{r['expected_expression']}` |" for r in mapping["mappings"]]
    rows += ["", "C4 has two assertions: membership and new-value lookup. C3 applies to all four scenarios.",
             "KeyError on target lookup is C2 PASS for the three expired scenarios. Unexpected exceptions (including library AssertionError) are ERROR.",
             "A missing survivor is a designated C3 failure; a runtime exception other than KeyError is ERROR.",
             "Overall ERROR takes precedence over FAIL; individual observations/assertions remain recorded.", "",
             "## Corrected lookup, equality and diagnostics", "",
             "Successful lookup, KeyError and unexpected exception are separate outcomes. C2 fails for every successful return without evaluating that value's equality.",
             "C3/C4 compare raw returned values with the approved expected values using Python == and truth conversion. Equality-compatible subclasses are accepted.",
             "Exceptions during equality or ambiguous truth conversion are equality_evaluation ERRORs; other applicable assertions still run.",
             "Setup uses the same equality rules but any unmet setup precondition remains setup ERROR, never a designated regression failure.",
             "Diagnostics never call user repr/str or traverse returned containers. Exact builtin JSON scalars are bounded; all other values are marked opaque.",
             "Diagnostic type branches do not restrict the claim predicates. Raw returned objects never enter serialized results.",
             "Exception messages/types are intentionally omitted to avoid user conversion hooks; fixed error stages identify lookup, membership, equality, setup, assignment and harness failures.",
             "Equality itself may invoke user code; this benign-case check is not a hostile-code sandbox. A trusted runner must enforce a timeout.", "",
             "## Static API and template validation", "",
             "A and B: local constructor signature accepts maxsize/ttu/timer; mapping methods have compatible arities; ttu is a property.",
             "The check supplies callbacks only at construction and never writes any cache attribute.",
             "Exact byte regeneration PASS; AST regeneration PASS; Python compilation PASS without execution.",
             f"Finite scope: {validation['scenario_count']} scenarios, {validation['scoped_assertion_count']} scoped assertions, C1–C4 covered.",
             "Source snippets/hashes and API diagnostics are in conformance.json. These are static diagnostics, not runtime compatibility or semantic proof.",
             "Behavioral support: HUMAN_APPROVED, NOT_MECHANICALLY_PROVED. Model proposal quality remains NOT_EVALUATED.", "",
             "## Execution integrity and remaining gates", "",
             "Standalone execution requires -I -S -B, a snapshot manifest and its expected hash. It verifies complete snapshot files before/after execution,",
             "and loaded cachetools paths/hashes in the same process. The future trusted runner must independently bind approved check bytes,",
             "manifest provenance, interpreter identity, sanitized environment, timeout and result classification. That runner is not yet implemented.",
             "No generated check has been run on A or B. No check approval, historical validation, activation, or future-patch results exist.",
             "Approve/reject with the CLI, your real identity and review minutes, and the exact check/checkpoint hashes shown by status.",
             "Approval here authorizes later historical validation; it does not itself validate behavior or activate the check.", "",
             "## Complete generated Python check", "", "```python", data.decode().rstrip(), "```", ""]
    return "\n".join(rows)
