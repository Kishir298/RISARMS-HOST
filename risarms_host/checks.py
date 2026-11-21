"""Operator checks run by ``risarms-host doctor``."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from . import __version__, compat
from .layout import DEPLOYMENT_FILES


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str = ""


def run_checks(root: Path) -> list[Check]:
    checks: list[Check] = []

    checks.append(
        Check(
            "python",
            sys.version_info >= (3, 10),
            f"{sys.version_info.major}.{sys.version_info.minor}",
        )
    )

    try:
        manifest = compat.load(root)
        version = compat.validate(manifest)
        checks.append(Check("compatibility", True, f"version {version}"))
    except compat.CompatibilityError as exc:
        version = None
        checks.append(Check("compatibility", False, str(exc)))

    if version is not None:
        checks.append(
            Check(
                "umbrella-version",
                version == __version__,
                f"risarms-host {__version__} vs compatibility {version}",
            )
        )

    for relative in DEPLOYMENT_FILES:
        checks.append(Check(relative, (root / relative).is_file(), relative))

    return checks


def workspace_checks(root: Path) -> list[Check]:
    from .layout import WORKSPACE_REPOS

    return [
        Check(component.name, component.check(root), component.path)
        for component in WORKSPACE_REPOS
    ]
