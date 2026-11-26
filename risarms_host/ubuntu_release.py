"""Additive Ubuntu candidate builder. Leaves the default Void release untouched."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import bundle, compat, revisions


def _project_version(path: Path) -> str:
    """Read ``project.version`` without requiring tomllib on Python 3.10."""
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:
        section = re.search(
            r"(?ms)^\[project\]\s*(.*?)(?=^\[|\Z)", text
        )
        if not section:
            raise ValueError(f"{path}: [project] section not found")
        match = re.search(
            r'(?m)^\s*version\s*=\s*([\'"])(?P<version>[^\'"]+)\1',
            section.group(1),
        )
        if not match:
            raise ValueError(f"{path}: project.version not found")
        return match.group("version")
    data = tomllib.loads(text)
    version = data.get("project", {}).get("version")
    if not isinstance(version, str) or not version:
        raise ValueError(f"{path}: project.version not found")
    return version


def manifest_for_ubuntu(original: dict) -> dict:
    data = json.loads(json.dumps(original))
    data["release_channel"] = "beta"
    data["server_deployment"] = {
        "os": "linux", "distribution": "ubuntu", "versions": ["24.04"],
        "architectures": ["x86_64"], "libc": "glibc", "init": "systemd",
        "install_methods": ["source-release-archive"],
        "notes": "Ubuntu port candidate; booted-system validation pending.",
    }
    data["supported_operating_systems"] = [
        entry for entry in data.get("supported_operating_systems", [])
        if entry.get("role") != "server"
    ] + [{**data["server_deployment"], "role": "server-candidate"}]
    data.setdefault("build_metadata", {})["artifact_naming"] = (
        "CORE-Server-{version}-ubuntu24.04-x86_64.tar.gz"
    )
    return data


def build(root: Path, out: Path) -> Path:
    root, out = root.resolve(), out.resolve()
    manifest = compat.load(root)
    version = compat.validate(manifest)  # Current default Void manifest is unchanged.
    lock = revisions.load(root)
    revisions.validate(lock, expected_version=version)
    out.mkdir(parents=True, exist_ok=True)
    name = f"CORE-Server-{version}-ubuntu24.04-x86_64"
    tree = out / name
    revisions.stage(root, tree, lock)
    try:
        for component in ("CORE-HOST", "CORE-CLIENT"):
            # Python 3.10 has no tomllib; _project_version has a stdlib fallback.
            actual = _project_version(tree / component / "pyproject.toml")
            if actual != version:
                raise ValueError(f"{component}: {actual} != {version}")
        candidate = manifest_for_ubuntu(manifest)
        (tree / "compatibility.json").write_text(json.dumps(candidate, indent=2) + "\n")
        lock["target"] = "ubuntu-24.04-x86_64-glibc-systemd"
        (tree / "components.lock.json").write_text(json.dumps(lock, indent=2) + "\n")
        shutil.copy2(root / "deployment/ubuntu/README.md", tree / "INSTALL.txt")
        archive = out / f"{name}.tar.gz"
        bundle._write_deterministic_tar(out, name, archive)
        second = out / ".rebuild.tar.gz"
        bundle._write_deterministic_tar(out, name, second)
        if archive.read_bytes() != second.read_bytes():
            raise ValueError("Archive reproducibility check failed")
        second.unlink()
        sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        (out / "SHA256SUMS").write_text(f"{sha}  {archive.name}\n")
        commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        (out / "ubuntu-provenance.json").write_text(json.dumps({
            "artifact": archive.name, "sha256": sha,
            "umbrella_base_commit": commit, "components": lock["components"],
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "validation": "source and static checks only; booted Ubuntu tests pending",
            "signature": "none",
        }, indent=2) + "\n")
        return archive
    finally:
        # The extracted sources are kept for inspection; no source or user data is deleted.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=Path("build/ubuntu"))
    args = parser.parse_args()
    print(build(args.root, args.out))


if __name__ == "__main__":
    main()
