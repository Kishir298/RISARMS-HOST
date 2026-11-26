"""Pinned component revisions for reproducible release assembly.

A CORE server release is no longer built from one repository. It is assembled
from six separately-versioned components, each pinned to an exact commit in
``components.lock.json``. Staging materialises those pins into the historical
bundle layout so ``deployment/void/install.sh`` keeps working unchanged.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .layout import (
    BUNDLE_COMPONENT_PATHS,
    STAGE_SERVICE_METADATA,
    STAGE_UMBRELLA_DIRS,
    STAGE_UMBRELLA_FILES,
)

LOCK_NAME = "components.lock.json"
REVISION_RE = re.compile(r"[0-9a-f]{40}")
REPOSITORY_RE = re.compile(r"https://[A-Za-z0-9._/-]+\.git")


class RevisionError(ValueError):
    """The component lock is missing, malformed or inconsistent."""


def _remove_read_only(func, path, _exc):
    """Clear Windows read-only attributes so rmtree can delete git objects."""
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    func(path)


@dataclass(frozen=True)
class PinnedComponent:
    """One component pinned to an exact commit."""

    name: str
    repository: str
    revision: str
    path: str

    def fetch_commands(self, destination: Path) -> list[list[str]]:
        target = destination / self.path
        return [
            ["git", "init", "-q", str(target)],
            ["git", "-C", str(target), "remote", "add", "origin", self.repository],
            [
                "git",
                "-C",
                str(target),
                "fetch",
                "--depth",
                "1",
                "--quiet",
                "origin",
                self.revision,
            ],
            [
                "git",
                "-C",
                str(target),
                "-c",
                "advice.detachedHead=false",
                "checkout",
                "--quiet",
                "--detach",
                "FETCH_HEAD",
            ],
        ]


def load(root: Path, name: str = LOCK_NAME) -> dict:
    path = Path(root) / name
    if not path.is_file():
        raise RevisionError(f"{name} not found in {root}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RevisionError(f"{name} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RevisionError(f"{name} must contain a JSON object")
    return data


def validate(lock: dict, expected_version: str | None = None) -> list[PinnedComponent]:
    """Return the pinned components, or raise :class:`RevisionError`."""
    version = lock.get("version")
    if not isinstance(version, str) or not version:
        raise RevisionError("components.lock.json is missing a version")
    if expected_version is not None and version != expected_version:
        raise RevisionError(
            f"components.lock.json version {version!r} != "
            f"compatibility version {expected_version!r}"
        )

    components = lock.get("components")
    if not isinstance(components, dict):
        raise RevisionError("components.lock.json is missing a components object")

    expected = set(BUNDLE_COMPONENT_PATHS)
    present = set(components)
    missing = sorted(expected - present)
    if missing:
        raise RevisionError("components.lock.json is missing: " + ", ".join(missing))
    unknown = sorted(present - expected)
    if unknown:
        raise RevisionError(
            "components.lock.json has unknown components: " + ", ".join(unknown)
        )

    pinned: list[PinnedComponent] = []
    for name in sorted(expected):
        entry = components[name]
        if not isinstance(entry, dict):
            raise RevisionError(f"component {name!r} must be an object")
        repository = entry.get("repository")
        if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
            raise RevisionError(
                f"component {name!r} repository must be an https .git URL"
            )
        revision = entry.get("revision")
        if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
            raise RevisionError(
                f"component {name!r} revision must be a full 40-character commit SHA"
            )
        path = entry.get("path")
        if path != BUNDLE_COMPONENT_PATHS[name]:
            raise RevisionError(
                f"component {name!r} path must be "
                f"{BUNDLE_COMPONENT_PATHS[name]!r}, got {path!r}"
            )
        pinned.append(PinnedComponent(name, repository, revision, path))
    return pinned


def _run(command: list[str]) -> None:
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:  # pragma: no cover - git is always present in CI
        raise RevisionError("git is required to stage pinned components") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RevisionError(
            f"git command failed ({' '.join(command)}): {detail}"
        ) from exc


def _head(target: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def stage(
    root: Path,
    destination: Path,
    lock: dict,
    run: Callable[[list[str]], None] | None = None,
) -> Path:
    """Materialise pinned components plus umbrella assets under ``destination``.

    The result is the historical bundle root layout (``CORE-HOST/``,
    ``CORE-CLIENT/``, ``services/``, ``deployment/``, ``compatibility.json``),
    with every component at the exact revision recorded in the lock.
    """
    root = Path(root)
    destination = Path(destination)
    pinned = validate(lock)

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    for name in STAGE_UMBRELLA_DIRS:
        source = root / name
        if not source.is_dir():
            raise RevisionError(f"umbrella source directory missing: {name}")
        shutil.copytree(source, destination / name)
    for name in STAGE_UMBRELLA_FILES:
        source = root / name
        if not source.is_file():
            raise RevisionError(f"umbrella source file missing: {name}")
        shutil.copy2(source, destination / name)

    services = destination / "services"
    services.mkdir(exist_ok=True)
    for name in STAGE_SERVICE_METADATA:
        source = root / "services" / name
        if source.is_file():
            shutil.copy2(source, services / name)

    execute = run or _run
    for component in pinned:
        for command in component.fetch_commands(destination):
            execute(command)
        target = destination / component.path
        head = _head(target)
        if head != component.revision:
            raise RevisionError(
                f"component {component.name!r} is at {head}, "
                f"expected {component.revision}"
            )
        # A release bundle ships sources, not their git metadata.
        git_dir = target / ".git"
        if git_dir.is_dir():
            shutil.rmtree(git_dir, onerror=_remove_read_only)

    return destination
