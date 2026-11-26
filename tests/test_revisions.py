import json
import shutil
import subprocess
from pathlib import Path

import pytest

from risarms_host import compat, revisions
from risarms_host.layout import BUNDLE_COMPONENT_PATHS

requires_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

GOOD_SHA = "a" * 40


def make_lock(**overrides) -> dict:
    components = {
        name: {
            "repository": f"https://github.com/Kishir298/{name.upper()}.git",
            "revision": GOOD_SHA,
            "path": path,
        }
        for name, path in BUNDLE_COMPONENT_PATHS.items()
    }
    components.update(overrides)
    return {
        "schema_version": 1,
        "release": "CORE Server",
        "version": "9.9.9",
        "components": components,
    }


def test_validate_accepts_complete_lock():
    pinned = revisions.validate(make_lock())
    assert [component.name for component in pinned] == sorted(BUNDLE_COMPONENT_PATHS)
    assert {component.path for component in pinned} == set(BUNDLE_COMPONENT_PATHS.values())


def test_validate_rejects_short_revision():
    lock = make_lock()
    lock["components"]["core-host"]["revision"] = "abc123"
    with pytest.raises(revisions.RevisionError, match="40-character"):
        revisions.validate(lock)


def test_validate_rejects_missing_component():
    lock = make_lock()
    del lock["components"]["asis"]
    with pytest.raises(revisions.RevisionError, match="rescs|asis"):
        revisions.validate(lock)


def test_validate_rejects_unknown_component():
    lock = make_lock(extra={"repository": "https://github.com/x/y.git",
                            "revision": GOOD_SHA, "path": "services/EXTRA"})
    with pytest.raises(revisions.RevisionError, match="unknown"):
        revisions.validate(lock)


def test_validate_rejects_wrong_path():
    lock = make_lock()
    lock["components"]["core-host"]["path"] = "CORE"
    with pytest.raises(revisions.RevisionError, match="path must be"):
        revisions.validate(lock)


def test_validate_rejects_non_https_repository():
    lock = make_lock()
    lock["components"]["rescs"]["repository"] = "git@github.com:Kishir298/RESCS.git"
    with pytest.raises(revisions.RevisionError, match="https"):
        revisions.validate(lock)


def test_validate_rejects_version_mismatch():
    with pytest.raises(revisions.RevisionError, match="!= compatibility version"):
        revisions.validate(make_lock(), expected_version="0.6.0")


def test_load_missing_lock(tmp_path):
    with pytest.raises(revisions.RevisionError, match="not found"):
        revisions.load(tmp_path)


def test_load_invalid_json(tmp_path):
    (tmp_path / revisions.LOCK_NAME).write_text("{not json", encoding="utf-8")
    with pytest.raises(revisions.RevisionError, match="not valid JSON"):
        revisions.load(tmp_path)


def test_repository_lock_matches_compatibility_manifest(tmp_path):
    root = Path(__file__).resolve().parents[1]
    pinned = revisions.validate(
        revisions.load(root), expected_version=compat.validate(compat.load(root))
    )
    assert len(pinned) == len(BUNDLE_COMPONENT_PATHS)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def make_repo(path: Path, files: dict[str, str]) -> str:
    path.mkdir(parents=True)
    _git("init", "-q", str(path))
    for name, content in files.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git("-C", str(path), "add", "-A")
    _git(
        "-C", str(path),
        "-c", "user.email=test@example.test",
        "-c", "user.name=Test",
        "commit", "-qm", "fixture",
    )
    return _git("-C", str(path), "rev-parse", "HEAD")


def make_umbrella(root: Path, lock: dict) -> None:
    (root / "deployment" / "void").mkdir(parents=True)
    (root / "deployment" / "void" / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "services").mkdir()
    (root / "services" / "SOURCE-PROVENANCE.json").write_text("{}", encoding="utf-8")
    (root / revisions.LOCK_NAME).write_text(json.dumps(lock), encoding="utf-8")
    (root / compat.MANIFEST_NAME).write_text(
        json.dumps(
            {
                "version": "9.9.9",
                "release_channel": "beta",
                "server_deployment": {"distribution": "void", "architectures": ["x86_64"]},
                "components": {"host": {"version": "9.9.9"}},
            }
        ),
        encoding="utf-8",
    )


@requires_git
def test_stage_materialises_pinned_components(tmp_path):
    repos: dict[str, Path] = {}
    revisions_by_name: dict[str, str] = {}
    files = {
        "core-host": {"core/web/portal.html": "<html/>", "pyproject.toml": "[project]\n"},
        "core-client": {"client/entrypoint.py": "def main():\n"},
        "tiviss-client": {"pyproject.toml": "[project]\n"},
        "rescs": {"pyproject.toml": "[project]\n"},
        "ascs": {"pyproject.toml": "[project]\n"},
        "asis": {"pyproject.toml": "[project]\n"},
        "tiviss-host": {"pyproject.toml": "[project]\n"},
    }
    lock = make_lock()
    for name, paths in files.items():
        repo = tmp_path / "repos" / name
        revisions_by_name[name] = make_repo(repo, paths)
        repos[lock["components"][name]["repository"]] = repo
        lock["components"][name]["revision"] = revisions_by_name[name]

    umbrella = tmp_path / "umbrella"
    make_umbrella(umbrella, lock)

    def runner(command: list[str]) -> None:
        rewritten = [
            str(repos[arg]) if arg in repos else arg for arg in command
        ]
        revisions._run(rewritten)

    destination = revisions.stage(umbrella, tmp_path / "stage", lock, run=runner)

    for name, paths in files.items():
        for relative in paths:
            assert (destination / BUNDLE_COMPONENT_PATHS[name] / relative).is_file()
        assert not (destination / BUNDLE_COMPONENT_PATHS[name] / ".git").exists()
    assert (destination / "deployment" / "void" / "install.sh").is_file()
    assert (destination / "services" / "SOURCE-PROVENANCE.json").is_file()
    assert (destination / revisions.LOCK_NAME).is_file()

    second = revisions.stage(umbrella, tmp_path / "stage2", lock, run=runner)
    assert (second / "CORE-HOST" / "pyproject.toml").read_text() == (
        destination / "CORE-HOST" / "pyproject.toml"
    ).read_text()


@requires_git
def test_stage_fails_when_revision_unreachable(tmp_path):
    lock = make_lock()
    umbrella = tmp_path / "umbrella"
    make_umbrella(umbrella, lock)

    def runner(command: list[str]) -> None:
        revisions._run(command)

    with pytest.raises(revisions.RevisionError, match="git command failed"):
        revisions.stage(umbrella, tmp_path / "stage", lock, run=runner)
