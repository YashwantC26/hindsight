"""Isolated feasibility worker: one unchanged upstream test, never a product check."""
import argparse
import ast
import hashlib
import importlib
import io
import json
from pathlib import Path
import sys
import traceback
import unittest


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify_tree(root, manifest):
    records = manifest["files"]
    encoded = json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if sha(encoded) != manifest["files_sha256"]:
        raise ValueError("MANIFEST_INTEGRITY")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != set(records):
        raise ValueError("SNAPSHOT_FILE_SET")
    for name, record in records.items():
        path = root / name
        if path.is_symlink() or sha(path.read_bytes()) != record["sha256"]:
            raise ValueError("SNAPSHOT_BYTES: " + name)


def origins(target, fixed, target_manifest, fixed_manifest):
    checked = {}
    for name, module in list(sys.modules.items()):
        if not (name == "cachetools" or name.startswith("cachetools.")
                or name == "tests" or name.startswith("tests.")):
            continue
        root, manifest = (target, target_manifest) if name.startswith("cachetools") else (fixed, fixed_manifest)
        path = Path(module.__file__).resolve()
        if not path.is_relative_to(root):
            raise ValueError("IMPORT_ORIGIN: " + name)
        relative = path.relative_to(root).as_posix()
        if relative not in manifest["files"] or sha(path.read_bytes()) != manifest["files"][relative]["sha256"]:
            raise ValueError("IMPORT_HASH: " + name)
        checked[name] = {"file": str(path), "sha256": sha(path.read_bytes())}
    if "cachetools" not in checked or "tests.test_tlru" not in checked:
        raise ValueError("REQUIRED_IMPORT_MISSING")
    return checked


def main():
    parser = argparse.ArgumentParser()
    for name in ("target", "fixed", "target-manifest", "fixed-manifest"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    record = {"kind": "unchanged_upstream_reference", "counts_as_product_success": False,
              "counts_as_autonomous_success": False, "status": "ERROR"}
    try:
        target, fixed = args.target.resolve(), args.fixed.resolve()
        target_manifest = json.loads(args.target_manifest.read_text())
        fixed_manifest = json.loads(args.fixed_manifest.read_text())
        verify_tree(target, target_manifest)
        verify_tree(fixed, fixed_manifest)
        for path in (target / "src/cachetools").rglob("*.py"):
            ast.parse(path.read_bytes(), filename=str(path))
        sys.path[:0] = [str(target / "src"), str(fixed)]
        module = importlib.import_module("tests.test_tlru")
        record["imports_before"] = origins(target, fixed, target_manifest, fixed_manifest)
        method = "test_overwrite_existing_with_expired"
        suite = unittest.TestSuite([module.TLRUCacheTest(method)])
        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        record.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                      skipped=len(result.skipped), log=stream.getvalue())
        record["imports_after"] = origins(target, fixed, target_manifest, fixed_manifest)
        verify_tree(target, target_manifest)
        verify_tree(fixed, fixed_manifest)
        if result.testsRun != 1 or result.skipped or result.errors:
            record["status"] = "ERROR"
        elif result.failures:
            # Only this unchanged upstream method's assertion is a reference FAIL.
            if len(result.failures) == 1 and 'self.assertNotIn(1, cache)' in result.failures[0][1]:
                record["status"] = "FAIL"
            else:
                record["status"] = "ERROR"
        elif result.wasSuccessful():
            record["status"] = "PASS"
    except Exception as exc:
        record.update(status="ERROR", exception_type=type(exc).__name__, error=str(exc),
                      traceback=traceback.format_exc())
    print(json.dumps(record, sort_keys=True))
    return {"PASS": 0, "FAIL": 1}.get(record["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
