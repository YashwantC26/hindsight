"""Read exact known Git objects; never execute or alter the research archive."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import subprocess

from common import BUGGY, FIXED, REPOSITORY, digest, now, read, sha, write, write_bytes


def git(repository, *args):
    return subprocess.check_output(
        ["git", "-C", str(repository), *args],
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, timeout=30,
    )


def export(repository, revision, destination):
    """Blob extraction bypasses export-ignore/export-subst without rewriting bytes."""
    if destination.exists():
        raise ValueError("Snapshot already exists")
    records = {}
    for record in git(repository, "ls-tree", "-rz", "--full-tree", revision).split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        name = raw_path.decode("utf-8")
        path = PurePosixPath(name)
        if (kind != "blob" or mode not in ("100644", "100755") or path.is_absolute()
                or ".." in path.parts):
            raise ValueError("Unsupported snapshot entry: " + name)
        data = git(repository, "cat-file", "blob", oid)
        actual_oid = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        if actual_oid != oid:
            raise ValueError("Git object content mismatch")
        target = destination / name
        write_bytes(target, data)
        target.chmod(0o755 if mode == "100755" else 0o644)
        records[name] = {"git_blob_sha1": oid, "git_mode": mode,
                         "size": len(data), "sha256": sha(data)}
    if not records:
        raise ValueError("Empty snapshot")
    manifest = {"repository": REPOSITORY, "revision": revision,
                "files": records, "files_sha256": digest(records)}
    verify_snapshot(destination, manifest)
    return manifest


def verify_snapshot(root, manifest):
    expected = manifest["files"]
    if digest(expected) != manifest["files_sha256"]:
        raise ValueError("Snapshot manifest integrity failure")
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() or p.is_symlink()}
    if actual != set(expected):
        raise ValueError("Snapshot file set mismatch")
    for name, record in expected.items():
        path = root / name
        if path.is_symlink() or sha(path.read_bytes()) != record["sha256"]:
            raise ValueError("Snapshot source mismatch: " + name)


def acquire(run, repository):
    parents = git(repository, "show", "-s", "--format=%P", FIXED).decode().strip().split()
    if parents != [BUGGY]:
        raise ValueError("The requested fixed commit does not have the exact single parent")
    for label, revision in (("A", BUGGY), ("B", FIXED)):
        if git(repository, "rev-parse", revision + "^{commit}").decode().strip() != revision:
            raise ValueError("Revision identity mismatch")
        manifest = export(repository, revision, run / "snapshots" / label)
        write(run / f"snapshot-{label}.json", manifest)
    record = {"acquired_at": now(), "repository": REPOSITORY,
              "local_object_source": str(repository.resolve()), "buggy": BUGGY, "fixed": FIXED,
              "direct_parent_verified": True, "method": "complete Git blob extraction; no archive transformations",
              "snapshot_manifests": {label: sha((run / f"snapshot-{label}.json").read_bytes()) for label in ("A", "B")}}
    write(run / "acquisition.json", record)
    return record


def verify_acquisition(run):
    acquisition = read(run / "acquisition.json")
    if (acquisition["buggy"], acquisition["fixed"]) != (BUGGY, FIXED):
        raise ValueError("Wrong historical pair")
    for label, revision in (("A", BUGGY), ("B", FIXED)):
        path = run / f"snapshot-{label}.json"
        if sha(path.read_bytes()) != acquisition["snapshot_manifests"][label]:
            raise ValueError("Acquisition manifest changed")
        manifest = read(path)
        if manifest["revision"] != revision or manifest["repository"] != REPOSITORY:
            raise ValueError("Snapshot revision mismatch")
        verify_snapshot(run / "snapshots" / label, manifest)
    return acquisition
