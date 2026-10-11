"""Trusted stdlib wrapper; executes exactly one verified immutable source buffer."""
import _imp
import argparse
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sys
import sysconfig

FROZEN_ALIASES = {"importlib._bootstrap": "_frozen_importlib",
                  "importlib._bootstrap_external": "_frozen_importlib_external", "os.path": "posixpath"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    return digest(Path(path).read_bytes())


def decode_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("NONFINITE_JSON")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)


def identity():
    executable = Path(sys.executable).resolve()
    return {"executable": str(executable), "sha256": sha(executable), "version": sys.version,
            "implementation": platform.python_implementation(),
            "flags": {"isolated": bool(sys.flags.isolated), "no_site": bool(sys.flags.no_site),
                      "no_bytecode": bool(sys.dont_write_bytecode)}}


class OutputLimitError(ValueError):
    pass


class BoundedText(io.StringIO):
    def __init__(self, limit):
        super().__init__()
        self.limit, self.used, self.overflowed = limit, 0, False

    def write(self, value):
        size = len(value.encode("utf-8"))
        if self.used + size > self.limit:
            self.overflowed = True
            raise OutputLimitError("CHECK_OUTPUT_LIMIT")
        self.used += size
        return super().write(value)


def execute_verified(source, path, expected_sha256):
    """The hash and compiler consume the same immutable bytes, never a path reload."""
    if type(source) is not bytes or digest(source) != expected_sha256:
        raise ValueError("CHECK_BUFFER_HASH_MISMATCH")
    namespace = {"__name__": "HINDSIGHT_APPROVED_CHECK", "__file__": str(path),
                 "__package__": None, "__spec__": None, "__loader__": None, "__cached__": None}
    exec(compile(source, str(path), "exec"), namespace)
    return namespace["main"]()


def module_inventory(root, manifest):
    files, nonfiles = {}, {}
    root = root.resolve()
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    for name, module in list(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        spec = getattr(module, "__spec__", None)
        spec_origin, canonical = getattr(spec, "origin", None), getattr(spec, "name", name)
        if spec_origin == "built-in" and _imp.is_builtin(name) and canonical == name and not origin:
            nonfiles[name] = {"kind": "built-in", "canonical_name": name}
            continue
        if spec_origin == "frozen" and _imp.is_frozen(canonical) and (name == canonical or FROZEN_ALIASES.get(name) == canonical):
            nonfiles[name] = {"kind": "frozen", "canonical_name": canonical}
            continue
        if not origin or origin.startswith("<"):
            raise ValueError("UNEXPLAINED_MODULE_ORIGIN")
        path = Path(origin).resolve()
        if name == "__main__":
            allowed = path == Path(__file__).resolve()
        elif name == "cachetools" or name.startswith("cachetools."):
            allowed = path.is_relative_to(root) and path.relative_to(root).as_posix() in manifest["files"]
            if allowed:
                allowed = sha(path) == manifest["files"][path.relative_to(root).as_posix()]["sha256"]
        else:
            allowed = path.is_relative_to(stdlib) and not any(p in ("site-packages", "dist-packages") for p in path.parts)
        if not allowed:
            raise ValueError("UNEXPECTED_MODULE_ORIGIN")
        files[name] = {"path": str(path), "sha256": sha(path)}
    return files, nonfiles


def raw_evidence(stdout, stderr):
    result = {"check_output_overflow": bool((stdout and stdout.overflowed) or (stderr and stderr.overflowed))}
    for name, stream in (("stdout", stdout), ("stderr", stderr)):
        raw = stream.getvalue().encode("utf-8") if stream is not None else b""
        result["check_" + name + "_b64"] = base64.b64encode(raw).decode("ascii")
        result["check_" + name + "_sha256"] = digest(raw)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    stage, request, stdout, stderr = "integrity", {}, None, None
    try:
        raw_request = args.request.read_bytes()
        if digest(raw_request) != args.request_sha256:
            raise ValueError("REQUEST_HASH_MISMATCH")
        request = decode_json(raw_request)
        if identity() != request["interpreter"] or not all(identity()["flags"].values()):
            raise ValueError("INTERPRETER_MISMATCH")
        check, manifest_path = Path(request["check_path"]), Path(request["manifest_path"])
        source = check.read_bytes()  # The only source read used for execution.
        manifest_raw = manifest_path.read_bytes()
        if digest(source) != request["check_sha256"] or digest(manifest_raw) != request["manifest_sha256"]:
            raise ValueError("LAUNCH_INPUT_HASH_MISMATCH")
        manifest = decode_json(manifest_raw)
        stdout, stderr = BoundedText(request["check_stdout_limit"]), BoundedText(request["check_stderr_limit"])
        sys.argv = [str(check), "--snapshot-root", request["snapshot_root"],
                    "--snapshot-manifest", str(manifest_path), "--manifest-sha256", request["manifest_sha256"]]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            stage = "check_execution"
            exit_code = execute_verified(source, check, request["check_sha256"])
        stage = "integrity"
        if stdout.overflowed or stderr.overflowed:
            raise OutputLimitError("CHECK_OUTPUT_LIMIT")
        if stderr.getvalue():
            raise ValueError("UNEXPECTED_CHECK_STDERR")
        output = decode_json(stdout.getvalue().encode("utf-8"))
        if sha(check) != request["check_sha256"] or sha(manifest_path) != request["manifest_sha256"]:
            raise ValueError("LAUNCH_INPUT_CHANGED")
        modules, nonfiles = module_inventory(Path(request["snapshot_root"]), manifest)
        result = {"kind": "hindsight_trusted_execution_v2", "interpreter": identity(), "pid": os.getpid(),
                  "invocation_id": request["invocation_id"], "request_sha256": args.request_sha256,
                  "check_sha256": digest(source), "manifest_sha256": request["manifest_sha256"],
                  "environment": dict(os.environ), "cwd": str(Path.cwd().resolve()),
                  "module_files": modules, "nonfile_modules": nonfiles, "result": output,
                  **raw_evidence(stdout, stderr)}
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return exit_code
    except Exception as exc:
        result = {"kind": "hindsight_worker_error_v2", "status": "ERROR", "error_type": type(exc).__name__,
                  "stage": "output_limit" if isinstance(exc, OutputLimitError) or
                      (stdout is not None and stdout.overflowed) or (stderr is not None and stderr.overflowed) else stage,
                  "invocation_id": request.get("invocation_id"), "request_sha256": args.request_sha256,
                  **raw_evidence(stdout, stderr)}
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
