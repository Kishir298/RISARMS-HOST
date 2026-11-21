"""compatibility.json loading and validation."""

from __future__ import annotations

import json
import re
from pathlib import Path

MANIFEST_NAME = "compatibility.json"
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


class CompatibilityError(ValueError):
    """compatibility.json is missing a required or well-formed field."""


def load(root: Path) -> dict:
    path = root / MANIFEST_NAME
    if not path.is_file():
        raise CompatibilityError(f"{MANIFEST_NAME} not found in {root}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompatibilityError(f"{MANIFEST_NAME} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CompatibilityError(f"{MANIFEST_NAME} must contain a JSON object")
    return data


def validate(manifest: dict) -> str:
    version = manifest.get("version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        raise CompatibilityError(f"Unsupported version: {version!r}")
    channel = manifest.get("release_channel")
    if channel not in {"stable", "beta"}:
        raise CompatibilityError(f"Unsupported release channel: {channel!r}")
    server = manifest.get("server_deployment")
    if not isinstance(server, dict):
        raise CompatibilityError("server_deployment is missing")
    if server.get("distribution") != "void":
        raise CompatibilityError("server_deployment must target Void Linux")
    if server.get("architectures") != ["x86_64"]:
        raise CompatibilityError("server_deployment must target x86_64")
    host = manifest.get("components", {}).get("host", {})
    if host.get("version") != version:
        raise CompatibilityError(
            f"components.host.version {host.get('version')!r} != {version!r}"
        )
    return version
