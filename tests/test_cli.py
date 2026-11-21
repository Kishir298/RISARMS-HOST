import json
from pathlib import Path

from risarms_host import __version__
from risarms_host.cli import main
from tests.test_bundle import make_source

REPO_ROOT = str(Path(__file__).resolve().parents[1])


def test_version_prints_release_info(capsys):
    assert main(["version", "--root", REPO_ROOT]) == 0
    out = capsys.readouterr().out
    assert f"risarms-host {__version__}" in out
    assert "void x86_64" in out
    assert "core 0.6.0" in out


def test_version_fails_without_manifest(tmp_path, capsys):
    assert main(["version", "--root", str(tmp_path)]) == 1
    assert "error:" in capsys.readouterr().err


def test_components_text_reports_missing_required(tmp_path, capsys):
    (tmp_path / "CORE-HOST").mkdir()
    (tmp_path / "CORE-HOST" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert main(["components", "--root", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "[ok] core-host" in captured.out
    assert "[FAIL] rescs" in captured.out
    assert "missing required" in captured.err


def test_components_json_for_complete_workspace(tmp_path, capsys):
    for name in ("CORE-HOST", "CORE-CLIENT", "RISARMS-ui", "RESCS", "TIVISS-HOST"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert main(["components", "--root", str(tmp_path), "--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["core-host"]["present"] is True
    assert payload["tiviss-client"]["present"] is False


def test_doctor_passes_on_umbrella_repo(capsys):
    assert main(["doctor", "--root", REPO_ROOT]) == 0
    out = capsys.readouterr().out
    assert "[ok] compatibility" in out
    assert "[ok] umbrella-version" in out
    assert "[FAIL]" not in out


def test_doctor_fails_on_empty_root(tmp_path, capsys):
    assert main(["doctor", "--root", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert "[FAIL] compatibility" in captured.out
    assert "[FAIL] deployment/void/install.sh" in captured.out


def test_doctor_workspace_flag_checks_siblings(tmp_path, capsys):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "RESCS").mkdir()
    (tmp_path / "workspace" / "RESCS" / "pyproject.toml").write_text(
        "[project]\n", encoding="utf-8"
    )
    assert main(["doctor", "--root", REPO_ROOT, "--workspace", str(tmp_path / "workspace")]) == 1
    out = capsys.readouterr().out
    assert "[ok] rescs" in out
    assert "[FAIL] core-host" in out


def test_bundle_command_writes_stage(tmp_path, capsys):
    make_source(tmp_path)
    out = tmp_path / "out"
    assert main(["bundle", "--root", str(tmp_path), "--out", str(out)]) == 0
    assert (out / "CORE-Server-9.9.9-void-x86_64" / "INSTALL.txt").is_file()
    assert capsys.readouterr().out.strip().endswith("CORE-Server-9.9.9-void-x86_64")


def test_bundle_command_reports_missing_sources(tmp_path, capsys):
    assert main(["bundle", "--root", str(tmp_path), "--out", str(tmp_path / "out")]) == 1
    assert "bundle failed:" in capsys.readouterr().err
