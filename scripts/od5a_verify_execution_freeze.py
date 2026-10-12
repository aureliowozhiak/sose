#!/usr/bin/env python3
"""Independent cold-start OD-5a freeze verifier. Admission is not DOE approval.

The stdlib-only bootstrap verifies every executable source byte and the
verifier's own manifest-bound hash BEFORE loading SOSE from --root.
"""
from __future__ import annotations

import sys

# sys is built in; reject nonisolated startup BEFORE importing any file-backed
# stdlib module. Python -I ignores PYTHONPATH, user-site and unsafe script dirs.
# A nonisolated interpreter may execute sitecustomize before this script, so
# the supported scientific invocation MUST use -I from process startup.
if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
    raise RuntimeError(
        "OD-5a independent freeze bootstrap requires isolated Python (-I -B)"
    )
sys.dont_write_bytecode = True

import argparse
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess


def _run_git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, val in pairs:
        if key in result:
            raise ValueError(f"duplicate frozen manifest field: {key}")
        result[key] = val
    return result


def _bootstrap(root: Path, manifest_path: Path) -> tuple[dict[str, object], bytes]:
    """Return manifest and verified source *bytes*, no checkout imports."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique)
    if not isinstance(payload, dict):
        raise ValueError("execution-freeze manifest must be a JSON object")
    actual_root = Path(os.fsdecode(_run_git(root, "rev-parse", "--show-toplevel").strip())).resolve()
    if root != actual_root:
        raise ValueError("freeze root must match the Git repository top level")

    # The bootstrap itself must be bound to the prospectively frozen verifier
    # artifact; module code will only be executed after this proof succeeds.
    verifier_hash = sha256(Path(__file__).read_bytes()).hexdigest()
    if verifier_hash != payload.get("verifier_sha256"):
        raise ValueError("independent verifier_sha256 does not match bootstrap bytes")

    for name, field in (
        ("uv.lock", "uv_lock_sha256"),
        ("docs/organizational/preregistration/od5a-structure-capacity-v2-design.json",
         "preregistration_sha256"),
    ):
        if sha256((root / name).read_bytes()).hexdigest() != payload.get(field):
            raise ValueError(f"independently frozen file bytes mismatch: {name}")

    source = root / "src/sose"
    for item in (root / "src", source, source / "organizational",
                 source / "organizational/od5a_execution_freeze.py"):
        if item.is_symlink():
            raise ValueError("source symlink before verifier import")
    if not source.is_dir():
        raise ValueError("frozen source tree is missing")
    declared_tree = payload.get("source_tree_oid")
    if not isinstance(declared_tree, str) or re.fullmatch(r"[0-9a-f]{40}", declared_tree) is None:
        raise ValueError("frozen source_tree_oid is malformed")
    actual_tree = _run_git(root, "rev-parse", "HEAD:src/sose").strip().decode("ascii")
    if actual_tree != declared_tree:
        raise ValueError("source tree OID differs from frozen Git tree")
    dirty = _run_git(
        root, "status", "--porcelain", "--untracked-files=all",
        "--ignored=matching", "--", "src/sose",
    )
    if dirty.strip():
        raise ValueError("dirty source checkout contains modified, untracked or ignored files")

    entries = _run_git(root, "ls-tree", "-rz", "HEAD", "--", "src/sose")
    if not entries:
        raise ValueError("frozen source tree has no tracked source")
    verified_module_path = source / "organizational/od5a_execution_freeze.py"
    verified_module_bytes: bytes | None = None
    for entry in entries.split(b"\x00"):
        if not entry:
            continue
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, git_oid = meta.split(b" ", 2)
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("source symlinks or unsupported frozen Git entries")
        file = root / os.fsdecode(raw_path)
        try:
            st = file.lstat()
        except FileNotFoundError as exc:
            raise ValueError("dirty missing tracked source") from exc
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("source symlink or changed tracked file kind")
        if bool(st.st_mode & 0o111) != (mode == b"100755"):
            raise ValueError("dirty tracked source executable bit changed")
        content = file.read_bytes()
        actual_oid = sha1(
            b"blob " + str(len(content)).encode("ascii") + b"\x00" + content
        ).hexdigest().encode("ascii")
        if actual_oid != git_oid:
            raise ValueError("dirty tracked source byte mismatch with frozen Git blob")
        if file == verified_module_path:
            verified_module_bytes = content
    if verified_module_bytes is None:
        raise ValueError("frozen verifier module is not tracked in Git source tree")
    return payload, verified_module_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    # Execute ONLY the exact source bytes attested above. Do not insert src/
    # into sys.path or run sose/organizational/__init__.py: unbound sibling
    # modules (e.g. src/pydantic.py) must never become import candidates.
    raw, verified_source = _bootstrap(root, args.manifest.resolve())
    if any(name == "sose" or name.startswith("sose.") for name in sys.modules):
        raise RuntimeError("SOSE imported before frozen checkout was validated")
    from types import ModuleType

    target = root / "src/sose/organizational/od5a_execution_freeze.py"
    verifier = ModuleType("_od5a_independently_verified_module")
    verifier.__file__ = str(target)
    exec(compile(verified_source, str(target), "exec"), verifier.__dict__)
    payload, digest = verifier.load_od5a_execution_freeze(args.manifest)
    if payload != raw:
        raise RuntimeError("frozen manifest changed between preflight and admission")
    if verifier.verify_od5a_checkout_identity(payload, root) != digest:
        raise RuntimeError("manifest digest changed during checkout verification")
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
