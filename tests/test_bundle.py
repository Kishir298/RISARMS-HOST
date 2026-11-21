import hashlib
import json
import tarfile
from pathlib import Path

import pytest

from risarms_host import bundle, compat
from risarms_host.layout import BUNDLE_REQUIREMENTS

PORTAL = "core/web/portal.html"
INSTALL_SH = "deployment/void/install.sh"


def make_source(root: Path) -> None:
    (root / "CORE-HOST" / PORTAL).parent.mkdir(parents=True)
    (root / "CORE-HOST" / PORTAL).write_text("<html/>", encoding="utf-8")
    (root / "CORE-CLIENT" / "client").mkdir(parents=True)
    (root / "CORE-CLIENT" / "client" / "entrypoint.py").write_text(
        "def main():\n", encoding="utf-8"
    )
    (root / "services" / "RESCS").mkdir(parents=True)
    (root / "services" / "RESCS" / "pyproject.toml").write_text(
        "[project]\n", encoding="utf-8"
    )
    (root / "deployment" / "void").mkdir(parents=True)
    (root / INSTALL_SH).write_text("#!/bin/sh\n", encoding="utf-8")
    (root / "README.md").write_text("# CORE\n", encoding="utf-8")
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


def test_missing_sources_reported(tmp_path):
    expected = [component.path for component in BUNDLE_REQUIREMENTS]
    assert bundle.missing_sources(tmp_path) == expected


def test_assemble_stages_release_layout(tmp_path):
    make_source(tmp_path)
    stage = bundle.assemble(tmp_path, tmp_path / "out")
    assert stage.name == "CORE-Server-9.9.9-void-x86_64"
    assert (stage / "CORE-HOST" / PORTAL).is_file()
    assert (stage / INSTALL_SH).is_file()
    assert (stage / "README.md").is_file()
    install_txt = (stage / "INSTALL.txt").read_text(encoding="utf-8")
    assert "CORE Server 9.9.9" in install_txt
    assert "sudo ./deployment/void/install.sh" in install_txt


def test_assemble_fails_when_component_missing(tmp_path):
    make_source(tmp_path)
    (tmp_path / "CORE-HOST" / PORTAL).unlink()
    with pytest.raises(bundle.BundleError, match="CORE-HOST"):
        bundle.assemble(tmp_path, tmp_path / "out")


def test_assemble_rejects_invalid_manifest(tmp_path):
    make_source(tmp_path)
    (tmp_path / compat.MANIFEST_NAME).write_text(
        json.dumps({"version": "nope"}), encoding="utf-8"
    )
    with pytest.raises(compat.CompatibilityError):
        bundle.assemble(tmp_path, tmp_path / "out")


def test_tar_output_with_checksum(tmp_path):
    make_source(tmp_path)
    archive = bundle.assemble(tmp_path, tmp_path / "out", as_tar=True)
    assert archive.name == "CORE-Server-9.9.9-void-x86_64.tar.gz"
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = (tmp_path / "out" / "SHA256SUMS").read_text(encoding="utf-8")
    assert sums == f"{expected}  {archive.name}\n"
    member_root = archive.name[: -len(".tar.gz")]
    with tarfile.open(archive) as bundle_tar:
        names = bundle_tar.getnames()
    assert f"{member_root}/{INSTALL_SH}" in names
    assert f"{member_root}/INSTALL.txt" in names
