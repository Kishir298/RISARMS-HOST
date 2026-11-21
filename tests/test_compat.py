import json
from pathlib import Path

import pytest

from risarms_host import __version__, compat

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_shipped_manifest_validates():
    manifest = compat.load(REPO_ROOT)
    assert compat.validate(manifest) == "0.6.0"


def test_umbrella_version_matches_manifest():
    assert compat.validate(compat.load(REPO_ROOT)) == __version__


def test_missing_manifest_fails(tmp_path):
    with pytest.raises(compat.CompatibilityError, match="not found"):
        compat.load(tmp_path)


def test_invalid_json_fails(tmp_path):
    (tmp_path / compat.MANIFEST_NAME).write_text("{nope", encoding="utf-8")
    with pytest.raises(compat.CompatibilityError, match="not valid JSON"):
        compat.load(tmp_path)


def test_manifest_must_be_object(tmp_path):
    (tmp_path / compat.MANIFEST_NAME).write_text("[]", encoding="utf-8")
    with pytest.raises(compat.CompatibilityError, match="JSON object"):
        compat.load(tmp_path)


def _manifest(**overrides):
    manifest = {
        "version": "9.9.9",
        "release_channel": "beta",
        "server_deployment": {"distribution": "void", "architectures": ["x86_64"]},
        "components": {"host": {"version": "9.9.9"}},
    }
    manifest.update(overrides)
    return manifest


def test_valid_manifest_returns_version():
    assert compat.validate(_manifest()) == "9.9.9"


@pytest.mark.parametrize(
    "overrides, match",
    [
        ({"version": "abc"}, "Unsupported version"),
        ({"release_channel": "nightly"}, "release channel"),
        ({"server_deployment": {"distribution": "debian", "architectures": ["x86_64"]}}, "Void"),
        ({"server_deployment": {"distribution": "void", "architectures": ["arm64"]}}, "x86_64"),
        ({"components": {"host": {"version": "1.0.0"}}}, "components.host.version"),
        ({"server_deployment": None}, "server_deployment"),
    ],
)
def test_invalid_manifests_fail(overrides, match):
    with pytest.raises(compat.CompatibilityError, match=match):
        compat.validate(_manifest(**overrides))


def test_shipped_manifest_is_stable_json():
    raw = json.loads((REPO_ROOT / compat.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert raw["project"] == "CORE"
    assert raw["runtime"]["minimum_version"] == "3.10"
