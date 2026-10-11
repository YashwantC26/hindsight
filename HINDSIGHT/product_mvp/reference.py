"""Checkpoint A: repeated reference feasibility, not generated-check validation."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

from common import HERE, REFERENCE, now, sha, write
from snapshots import verify_acquisition

ORDER = (("A", "B"), ("B", "A"), ("A", "B"))


def run_reference(run, label, timeout=10):
    command = [sys.executable, "-I", "-S", "-B", str(HERE / "reference_worker.py"),
               "--target", str(run / "snapshots" / label), "--fixed", str(run / "snapshots/B"),
               "--target-manifest", str(run / f"snapshot-{label}.json"),
               "--fixed-manifest", str(run / "snapshot-B.json")]
    env = {key: value for key, value in os.environ.items() if key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    record = {"label": label, "command": command, "timeout_seconds": timeout}
    try:
        completed = subprocess.run(command, cwd=run, env=env, capture_output=True, text=True, timeout=timeout)
        record.update(exit_code=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
        worker = json.loads(completed.stdout)
        expected_code = {"PASS": 0, "FAIL": 1, "ERROR": 2}.get(worker.get("status"))
        if (expected_code is None or completed.returncode != expected_code
                or worker.get("kind") != "unchanged_upstream_reference"):
            raise ValueError("Worker outcome/exit inconsistency")
        record.update(status=worker["status"], worker=worker)
    except subprocess.TimeoutExpired as exc:
        record.update(status="TIMEOUT", exit_code=None,
                      stdout=str(exc.stdout or ""), stderr=str(exc.stderr or ""))
    except (ValueError, OSError) as exc:
        record.update(status="ERROR", error=str(exc))
    return record


def feasibility(run):
    verify_acquisition(run)
    if (run / "reference-results.json").exists():
        raise ValueError("Feasibility result already frozen; use a new attempt")
    record = {"started_at": now(), "reference": REFERENCE, "counts_as_product_success": False,
              "counts_as_autonomous_success": False, "order": ORDER,
              "environment": {"python": sys.version, "executable": sys.executable,
                              "interpreter_sha256": sha(Path(sys.executable).resolve().read_bytes()),
                              "platform": platform.platform(), "dependencies": "stdlib only; -I -S -B"},
              "runner_sha256": sha((HERE / "reference_worker.py").read_bytes()), "runs": []}
    for pair, labels in enumerate(ORDER, 1):
        for label in labels:
            result = run_reference(run, label)
            record["runs"].append({"pair": pair, **result})
    record["accepted"] = all(r["status"] == ("FAIL" if r["label"] == "A" else "PASS")
                             for r in record["runs"])
    record["finished_at"] = now()
    write(run / "reference-results.json", record)
    write(run / "checkpoint-a.json", (
        {"status": "PASSED" if record["accepted"] else "FAILED_STOP",
         "reference_only": True, "A": [r["status"] for r in record["runs"] if r["label"] == "A"],
         "B": [r["status"] for r in record["runs"] if r["label"] == "B"]}))
    return record
