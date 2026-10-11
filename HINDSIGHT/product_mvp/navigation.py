"""Bounded indexing of one changed Python module and its known reference test."""
import ast
import re

from common import BUGGY, FIXED, PRODUCTION, REPOSITORY, sha

RELEVANT = (
    "Cache.__init__", "Cache.__getitem__", "Cache.__setitem__", "Cache.__delitem__", "Cache.__missing__",
    "_TimedCache.__init__", "_TimedCache.timer", "_TimedCache._Timer.__init__",
    "_TimedCache._Timer.__call__", "_TimedCache._Timer.__enter__", "_TimedCache._Timer.__exit__",
    "TLRUCache.__init__", "TLRUCache.__setitem__", "TLRUCache.__contains__",
    "TLRUCache.__getitem__", "TLRUCache.ttu", "TLRUCache.expire",
)


def index_source(data, revision, path):
    tree = ast.parse(data, filename=path)
    lines = data.decode().splitlines(keepends=True)
    symbols = {}

    def walk(nodes, prefix=""):
        for node in nodes:
            if not isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = prefix + node.name
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            quote = "".join(lines[start - 1:node.end_lineno])
            symbols[name] = {
                "qualified_name": name, "kind": type(node).__name__, "revision": revision,
                "path": path, "start_line": start, "end_line": node.end_lineno,
                "start_byte": len("".join(lines[:start - 1]).encode()),
                "end_byte": len("".join(lines[:node.end_lineno]).encode()),
                "quote": quote, "quote_sha256": sha(quote.encode()), "file_sha256": sha(data),
                "decorators": [ast.unparse(d) for d in node.decorator_list],
            }
            if isinstance(node, ast.ClassDef):
                symbols[name]["bases"] = [ast.unparse(b) for b in node.bases]
                walk(node.body, name + ".")
            else:
                symbols[name]["signature_syntax"] = ast.unparse(node.args)
    walk(tree.body)
    return symbols


def citation(data, revision, node):
    lines = data.decode().splitlines(keepends=True)
    quote = "".join(lines[node.lineno - 1:node.end_lineno])
    return {"revision": revision, "path": PRODUCTION, "start_line": node.lineno,
            "end_line": node.end_lineno, "quote": quote, "quote_sha256": sha(quote.encode()),
            "file_sha256": sha(data)}


def method_nodes(data):
    found = {}
    def walk(nodes, prefix=""):
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                walk(node.body, prefix + node.name + ".")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                found[prefix + node.name] = node
    walk(ast.parse(data).body)
    return found


def entity_origins(data, revision):
    methods = method_nodes(data)
    setter = methods["TLRUCache.__setitem__"]
    constructor = methods["TLRUCache.__init__"]
    context = next(n for n in ast.walk(setter) if isinstance(n, ast.With))
    expiry = next(n for n in ast.walk(setter) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "expires" for t in n.targets))
    ttu = next(n for n in ast.walk(constructor) if isinstance(n, ast.Assign)
               and any(ast.unparse(t) == "self.__ttu" for t in n.targets))
    guard = next(n for n in ast.walk(setter) if isinstance(n, ast.If)
                 and ast.unparse(n.test) == "not time < expires")
    parameters = {n.arg: n for n in setter.args.args}
    specs = [
        ("cache_receiver", "self", "parameter:TLRUCache.__setitem__.self", parameters["self"],
         "The receiving TLRUCache; behavioral interpretation requires developer review."),
        ("target_key", "key", "parameter:TLRUCache.__setitem__.key", parameters["key"], "The key being assigned."),
        ("incoming_replacement", "value", "parameter:TLRUCache.__setitem__.value", parameters["value"],
         "The incoming value, distinct from any previous value at this key."),
        ("current_time", "time", ast.unparse(context.items[0].context_expr), context.items[0].optional_vars,
         "Local binding produced by entering the timer context; fixture fixes the returned time."),
        ("incoming_expiry", "expires", ast.unparse(expiry.value), expiry,
         "Expiry calculated from incoming key/value/current time; callback behavior is a fixture assumption, not an AST proof."),
        ("expiry_callback", "self.__ttu", ast.unparse(ttu.value), ttu,
         "Callback supplied at construction; the public ttu property is read-only."),
        ("previous_entry_observation", "cache_getitem(self, key)", "Cache.__getitem__", methods["TLRUCache.__getitem__"],
         "Existing value observed via public lookup; this is a reviewer interpretation across local methods, not automatic alias proof."),
        ("expiry_branch", ast.unparse(guard.test), "TLRUCache.__setitem__ branch condition", guard.test,
         "The whole negated comparison occurs in source; occurrence is not a postcondition proof."),
    ]
    return [{"id": identity, "source_expression": expression, "origin_expression": origin,
             "syntax_status": "SOURCE_LOCATED", "meaning_origin": "operator_proposed",
             "interpretation": meaning, "behavioral_proof": "NOT_MECHANICALLY_PROVED",
             "citation": citation(data, revision, node)}
            for identity, expression, origin, node, meaning in specs]


def local_calls(data, revision):
    methods = method_nodes(data)
    records = []
    for name in ("TLRUCache.__init__", "TLRUCache.__setitem__", "TLRUCache.__contains__", "TLRUCache.__getitem__"):
        method = methods[name]
        defaults = dict(zip([a.arg for a in method.args.args][-len(method.args.defaults):], method.args.defaults)) if method.args.defaults else {}
        for node in ast.walk(method):
            if not isinstance(node, ast.Call):
                continue
            spelling = ast.unparse(node.func)
            if spelling in defaults:
                resolved = ast.unparse(defaults[spelling])
                kind = "source_default_alias"
            elif spelling in methods:
                resolved, kind = spelling, "explicit_local_definition"
            elif spelling == "self.expire":
                resolved, kind = "TLRUCache.expire", "case_specific_local_member_lookup"
            elif spelling == "self.timer":
                resolved, kind = "_TimedCache.timer → _TimedCache._Timer.__call__", "review_required_property_call"
            elif spelling == "self.__ttu":
                resolved, kind = "constructor argument ttu", "callback_behavior_unresolved"
            else:
                resolved, kind = None, "unresolved_call"
            records.append({"scope": name, "expression": ast.unparse(node), "target_syntax": spelling,
                            "resolved_to": resolved, "resolution_kind": kind,
                            "citation": citation(data, revision, node)})
    return records


def changed_ranges(diff, indexes):
    ranges = []
    for line in diff.splitlines():
        match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if not match:
            continue
        values = match.groups()
        for label, start, count in (("A", int(values[0]), int(values[1] or 1)),
                                    ("B", int(values[2]), int(values[3] or 1))):
            end = start + count - 1
            overlapping = [s["qualified_name"] for s in indexes[label].values()
                           if s["kind"] != "ClassDef" and count > 0
                           and s["start_line"] <= end and start <= s["end_line"]]
            ranges.append({"label": label, "start_line": start, "line_count": count,
                           "overlapping_definitions": overlapping,
                           "note": "Diff hunk including context; no semantic inference"})
    return ranges


def analyze(run, production_diff):
    indexes, entities, calls = {}, {}, {}
    for label, revision in (("A", BUGGY), ("B", FIXED)):
        data = (run / "snapshots" / label / PRODUCTION).read_bytes()
        index = index_source(data, revision, PRODUCTION)
        if not set(RELEVANT).issubset(index):
            raise ValueError("Required local source definition missing")
        indexes[label] = index
        entities[label] = entity_origins(data, revision)
        calls[label] = local_calls(data, revision)
    reference_data = (run / "snapshots/B/tests/test_tlru.py").read_bytes()
    tests = index_source(reference_data, FIXED, "tests/test_tlru.py")
    return {"repository": REPOSITORY, "indexed_files": [PRODUCTION, "tests/test_tlru.py (known reference only)"],
            "symbols": indexes, "relevant_definitions": list(RELEVANT), "entities": entities,
            "local_call_relationships": calls, "changed_hunks": changed_ranges(production_diff, indexes),
            "reference": tests["TLRUCacheTest.test_overwrite_existing_with_expired"],
            "limits": ["One production module, no repository-wide graph",
                       "Call inventories are syntactic/local, not sound whole-program dispatch analysis",
                       "Callback and cross-method meanings require developer judgment",
                       "Upstream reference exposure is explicit; no fresh model inference or blindness claim"]}
