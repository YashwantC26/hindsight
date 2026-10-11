"""Small file primitives for the separate, checkpointed product attempt."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parent.parent
REPOSITORY = "https://github.com/tkem/cachetools"
BUGGY = "978d34d40cdbf3b4cbfce104f3166032cc4ea028"
FIXED = "c0fdf6abab38040947d6fe2e38c507401d5e2350"
PRODUCTION = "src/cachetools/__init__.py"
REFERENCE = "tests.test_tlru.TLRUCacheTest.test_overwrite_existing_with_expired"


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return sha(canonical(value))


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("Nonfinite JSON constant: " + value)
    return json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=invalid_constant)


def write_bytes(path, data):
    """Never overwrite an attempt artifact or follow an existing file symlink."""
    path = Path(path)
    resolved = path.resolve()
    for name in ("experiments", "product_planning"):
        if resolved.is_relative_to(WORKSPACE / "HINDSIGHT" / name):
            raise ValueError("Writes to preserved research/planning are forbidden")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def write(path, value):
    write_bytes(path, (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())


def run_directory(value):
    path = Path(value).resolve()
    root = HERE / "runs"
    if path == root or not path.is_relative_to(root):
        raise ValueError("Run outputs must be a new directory below product_mvp/runs")
    return path


def inventory(root):
    records = {}
    for path in sorted(Path(root).rglob("*")):
        key = path.relative_to(root).as_posix()
        if path.is_symlink():
            records[key] = {"kind": "symlink", "target": str(path.readlink())}
        elif path.is_file():
            records[key] = {"kind": "file", "size": path.stat().st_size,
                            "sha256": sha(path.read_bytes())}
        elif path.is_dir():
            records[key] = {"kind": "directory"}
        else:
            raise ValueError("Unsupported filesystem entry: " + str(path))
    return records


def initialize(run):
    if run.exists():
        raise ValueError("Use a new run directory; old attempts are never overwritten")
    baseline = {
        "created_at": now(),
        "trees": {name: inventory(WORKSPACE / "HINDSIGHT" / name)
                  for name in ("experiments", "product_planning")},
    }
    baseline["inventory_sha256"] = digest(baseline["trees"])
    write(run / "preservation-baseline.json", baseline)


def audit_preservation(run):
    baseline = read(run / "preservation-baseline.json")
    if digest(baseline["trees"]) != baseline["inventory_sha256"]:
        raise ValueError("Preservation baseline integrity failure")
    report = {"checked_at": now(), "baseline_sha256": sha((run / "preservation-baseline.json").read_bytes()),
              "unchanged": True, "trees": {}}
    for name, before in baseline["trees"].items():
        after = inventory(WORKSPACE / "HINDSIGHT" / name)
        changes = {"added": sorted(after.keys() - before.keys()),
                   "removed": sorted(before.keys() - after.keys()),
                   "changed": sorted(k for k in before.keys() & after.keys() if before[k] != after[k])}
        unchanged = not any(changes.values())
        report["unchanged"] &= unchanged
        report["trees"][name] = {"files": sum(v["kind"] == "file" for v in before.values()),
                                  "unchanged": unchanged, **changes}
    number = len(list(run.glob("preservation-audit.*.json"))) + 1
    write(run / f"preservation-audit.{number:03}.json", report)
    return report
