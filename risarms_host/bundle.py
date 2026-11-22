"""Assemble a release bundle from sibling component checkouts."""

from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import tarfile
from pathlib import Path

from . import compat, revisions
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
        if not source.exists():
            # The component lock is optional for ad-hoc bundles but required
            # for a release; assemble() validates it when it is present.
            if name == revisions.LOCK_NAME:
                continue
            raise BundleError(f"Missing release source: {name}")
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


def _source_date_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "")
    return int(raw) if raw.isdigit() else 0


def _write_deterministic_tar(parent: Path, base_dir: str, archive: Path) -> None:
    """Write a reproducible ``.tar.gz`` for ``parent / base_dir``.

    Entries are sorted, ownership is normalised and every timestamp comes from
    ``SOURCE_DATE_EPOCH`` (default 0), so re-assembling identical sources
    produces byte-identical archives.
    """
    tree = parent / base_dir
    mtime = _source_date_epoch()
    with archive.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=mtime) as gz:
            with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
                for path in sorted(
                    tree.rglob("*"),
                    key=lambda item: item.relative_to(parent).as_posix(),
                ):
                    arcname = path.relative_to(parent).as_posix()
                    info = tar.gettarinfo(str(path), arcname=arcname)
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    info.mtime = mtime
                    if path.is_symlink():
                        tar.addfile(info)
                    elif path.is_dir():
                        info.mode = 0o755
                        tar.addfile(info)
                    else:
                        info.mode = 0o755 if os.access(path, os.X_OK) else 0o644
                        with path.open("rb") as handle:
                            tar.addfile(info, handle)


def assemble(root: Path, out: Path, as_tar: bool = False) -> Path:
    missing = missing_sources(root)
    if missing:
        raise BundleError("Missing release sources: " + ", ".join(missing))
    manifest = compat.load(root)
    version = compat.validate(manifest)
    lock_path = root / revisions.LOCK_NAME
    if lock_path.is_file():
        # A release must record exactly which component commits it contains.
        revisions.validate(revisions.load(root), expected_version=version)

    name = f"CORE-Server-{version}-void-x86_64"
    stage = out / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    _stage(root, stage)
    (stage / "INSTALL.txt").write_text(_install_txt(version), encoding="utf-8")

    if not as_tar:
        return stage

    archive = out / f"{name}.tar.gz"
    _write_deterministic_tar(out, name, archive)
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
