#!/usr/bin/env python3
"""Checkpointed local HINDSIGHT product CLI; no research imports."""
import argparse
import json
from pathlib import Path

from common import audit_preservation, initialize, now, run_directory, write
from checks import check_exists, check_status, decide_check, generate_check
from reference import feasibility
from review import decide_semantics, prepare_review, status
from snapshots import acquire
from historical_runner import historical_validation, verify_trust


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    start = commands.add_parser("feasibility", help="New attempt: baseline, exact snapshots, unchanged upstream reference")
    start.add_argument("--repository", required=True, type=Path)
    start.add_argument("--run-dir", required=True)
    audit = commands.add_parser("audit", help="Verify all frozen research and planning bytes")
    audit.add_argument("--run-dir", required=True)
    prepare = commands.add_parser("prepare-review", help="Build Checkpoint B packet; stop for real developer review")
    prepare.add_argument("--run-dir", required=True)
    current = commands.add_parser("status", help="Show current review hashes and invalidation state")
    current.add_argument("--run-dir", required=True)
    generate = commands.add_parser("generate-check", help="After real semantic approval, emit Checkpoint C; do not execute")
    generate.add_argument("--run-dir", required=True)
    for name in ("runner-preflight", "validate-history"):
        command = commands.add_parser(name, help="Read-only runner integrity preflight" if name == "runner-preflight" else "Explicitly execute the approved historical protocol")
        command.add_argument("--run-dir", required=True)
        command.add_argument("--check-sha256", required=True)
        command.add_argument("--checkpoint-sha256", required=True)
        if name == "validate-history":
            command.add_argument("--confirm-historical-execution", action="store_true", required=True)
    for name, decision in (("approve-check", "approve"), ("reject-check", "reject")):
        command = commands.add_parser(name, help="Explicit developer " + decision + " of exact check and review packet")
        command.set_defaults(decision=decision)
        command.add_argument("--run-dir", required=True)
        command.add_argument("--reviewer", required=True)
        command.add_argument("--review-minutes", type=float, required=True)
        command.add_argument("--authorization-note", required=True)
        command.add_argument("--confirm-developer-decision", action="store_true", required=True)
        command.add_argument("--checkpoint-sha256", required=True)
        command.add_argument("--check-sha256", required=True)
    for name, decision in (("approve-semantics", "approve"), ("reject-semantics", "reject")):
        command = commands.add_parser(name, help="Explicit developer " + decision + " of exact contract/recipe bytes")
        command.set_defaults(decision=decision)
        command.add_argument("--run-dir", required=True)
        command.add_argument("--reviewer", required=True)
        command.add_argument("--review-minutes", type=float, required=True)
        command.add_argument("--authorization-note", required=True)
        command.add_argument("--confirm-developer-decision", action="store_true", required=True)
        for field in ("bundle", "evidence", "contract", "recipe"):
            command.add_argument("--" + field + "-sha256", required=True)
    args = parser.parse_args()
    run = run_directory(args.run_dir)
    if args.command == "feasibility":
        initialize(run)
        try:
            acquire(run, args.repository)
            result = feasibility(run)
            print(json.dumps({"checkpoint": "A", "accepted": result["accepted"],
                              "results": [{"pair": r["pair"], "label": r["label"], "status": r["status"]}
                                          for r in result["runs"]]}, indent=2))
            return 0 if result["accepted"] else 2
        except Exception as exc:
            write(run / "feasibility-error.json", {"at": now(), "status": "FAILED_STOP",
                                                   "type": type(exc).__name__, "error": str(exc)})
            raise
        finally:
            audit_preservation(run)
    if args.command == "audit":
        report = audit_preservation(run)
        print(json.dumps(report, indent=2))
        return 0 if report["unchanged"] else 2
    if args.command == "prepare-review":
        result = prepare_review(run)
    elif args.command == "status":
        result = status(run)
        if result["state"] == "SEMANTICS_APPROVED" and check_exists(run):
            result.update(check_status(run))
    elif args.command == "generate-check":
        result = generate_check(run)
    elif args.command == "runner-preflight":
        trust = verify_trust(run, args.check_sha256, args.checkpoint_sha256)
        result = {"status": "PREFLIGHT_PASSED", "check_sha256": trust["check_sha256"],
                  "checkpoint_sha256": trust["checkpoint_sha256"], "interpreter": trust["interpreter"],
                  "git_identity_verified": trust["git_identity_verified"], "historical_product_validation": "NOT_RUN"}
    elif args.command == "validate-history":
        report = historical_validation(run, {"check_sha256": args.check_sha256,
                                            "checkpoint_sha256": args.checkpoint_sha256},
                                       confirmed_execution=args.confirm_historical_execution)
        result = {"checkpoint": "D", "evaluation": report["evaluation"],
                  "runs": [{"label": r["label"], "status": r["status"]} for r in report["runs"]],
                  "results_path": str(run / "historical-validation-v1/historical-results.json"), "active": False}
    elif args.command in ("approve-check", "reject-check"):
        result = decide_check(run, decision=args.decision, reviewer=args.reviewer,
                              review_minutes=args.review_minutes, note=args.authorization_note,
                              expected_hashes={"checkpoint_sha256": args.checkpoint_sha256,
                                               "check_sha256": args.check_sha256},
                              confirmed=args.confirm_developer_decision)
    else:
        hashes = {field + "_sha256": getattr(args, field + "_sha256")
                  for field in ("bundle", "evidence", "contract", "recipe")}
        result = decide_semantics(run, decision=args.decision, reviewer=args.reviewer,
                                  review_minutes=args.review_minutes, note=args.authorization_note,
                                  expected_hashes=hashes, confirmed=args.confirm_developer_decision)
    print(json.dumps(result, indent=2))
    if args.command == "validate-history":
        return 0 if report["evaluation"]["accepted"] else 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "ERROR", "type": type(exc).__name__, "error": str(exc)}, indent=2))
        raise SystemExit(2)
