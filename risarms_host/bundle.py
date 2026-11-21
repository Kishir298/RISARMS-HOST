"""Assemble a release bundle from sibling component checkouts."""

from __future__ import annotations

import hashlib
import shutil
import tarfile
from pathlib import Path

from . import compat
from .layout import BUNDLE_OPTIONAL, BUNDLE_REQUIREMENTS, BUNDLE_SOURCES


class BundleError(RuntimeError):
    """A release bundle could not be assembled."""


def missing_sources(root: Path) -> list[str]:
    missing = []
    for component in BUNDLE_REQUIREMENTS:
        if not component.check(root):
            missing.append(component.path)
    return missing


def _stage(root: Path, stage: Path) -> None:
    for name in BUNDLE_SOURCES:
        source = root / name
        if source.is_dir():
            shutil.copytree(source, stage / name)
        else:
            shutil.copy2(source, stage / name)
    for name in BUNDLE_OPTIONAL:
        source = root / name
        if source.is_file():
            shutil.copy2(source, stage / name)


def _install_txt(version: str) -> str:
    return (
        f"CORE Server {version} (release bundle)\n"
        "Target: Void Linux x86_64 glibc only\n"
        "Install: sudo ./deployment/void/install.sh\n"
        "Diagnose: sudo risarms-doctor\n"
        "Backup: sudo risarms-backup\n"
        "Upgrade: sudo ./deployment/void/upgrade.sh <new-release-directory>\n"
        "Rollback: sudo risarms-rollback\n"
        "The installer does not enable services automatically.\n"
        "Review /etc/risarms/*.env and /etc/caddy/risarms/portal.caddy first.\n"
    )


def assemble(root: Path, out: Path, as_tar: bool = False) -> Path:
    missing = missing_sources(root)
    if missing:
        raise BundleError("Missing release sources: " + ", ".join(missing))
    manifest = compat.load(root)
    version = compat.validate(manifest)

    name = f"CORE-Server-{version}-void-x86_64"
    stage = out / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    _stage(root, stage)
    (stage / "INSTALL.txt").write_text(_install_txt(version), encoding="utf-8")

    if not as_tar:
        return stage

    archive = shutil.make_archive(str(out / name), "gztar", root_dir=out, base_dir=name)
    checksum = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    (out / "SHA256SUMS").write_text(
        f"{checksum}  {Path(archive).name}\n", encoding="utf-8"
    )
    with tarfile.open(archive) as bundle:
        if not any(
            member.name == f"{name}/deployment/void/install.sh"
            for member in bundle.getmembers()
        ):
            raise BundleError("Bundle does not contain deployment/void/install.sh")
    return Path(archive)
