"""Component layout shared by workspace discovery and release bundling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Component:
    name: str
    path: str
    required: bool = True
    marker: str = ""

    def check(self, root: Path) -> bool:
        target = root / self.path
        if not self.marker:
            return target.exists()
        return (target / self.marker).is_file()


WORKSPACE_REPOS = (
    Component("core-host", "CORE-HOST", marker="pyproject.toml"),
    Component("core-client", "CORE-CLIENT", marker="pyproject.toml"),
    Component("risarms-ui", "RISARMS-ui", marker="pyproject.toml"),
    Component("rescs", "RESCS", marker="pyproject.toml"),
    Component("tiviss-host", "TIVISS-HOST", marker="pyproject.toml"),
    Component("tiviss-client", "TIVISS-CLIENT", marker="pyproject.toml", required=False),
    Component("ascs", "ASCS", marker="pyproject.toml", required=False),
    Component("asis", "ASIS", marker="pyproject.toml", required=False),
    Component("risarms-docs", "RISARMS-DOCS", marker="README.md", required=False),
    Component("risarms-host", "RISARMS-HOST", marker="pyproject.toml", required=False),
)

BUNDLE_SOURCES = (
    "CORE-HOST",
    "CORE-CLIENT",
    "services",
    "deployment",
    "compatibility.json",
    "components.lock.json",
)

BUNDLE_OPTIONAL = ("README.md", "LICENSE")

#: Where each separately-versioned component lives inside an assembled bundle.
#: These are the paths a release stages from the component's owning repository
#: at the revision pinned in ``components.lock.json``; the umbrella only
#: contributes deployment assets, the compatibility manifest and the lock.
BUNDLE_COMPONENT_PATHS = {
    "core-host": "CORE-HOST",
    "core-client": "CORE-CLIENT",
    "rescs": "services/RESCS",
    "ascs": "services/ASCS",
    "asis": "services/ASIS",
    "tiviss-host": "services/TIVISS-HOST",
}

#: Umbrella-owned files copied verbatim into a staged release root.
STAGE_UMBRELLA_FILES = ("compatibility.json", "components.lock.json")
STAGE_UMBRELLA_DIRS = ("deployment",)
STAGE_SERVICE_METADATA = ("SOURCE-PROVENANCE.json",)

BUNDLE_REQUIREMENTS = (
    Component("core-host", "CORE-HOST", marker="core/web/portal.html"),
    Component("core-client", "CORE-CLIENT", marker="client/entrypoint.py"),
    Component("services", "services", marker="RESCS/pyproject.toml"),
    Component("deployment", "deployment", marker="void/install.sh"),
    Component("compatibility", "compatibility.json"),
)

DEPLOYMENT_FILES = (
    "deployment/void/install.sh",
    "deployment/void/doctor.sh",
    "deployment/void/etc/caddy/portal.caddy",
    "deployment/void/etc/nftables.d/risarms.nft",
    "deployment/void/etc/sv/risarms-core/run",
    "deployment/void/etc/sv/risarms-rescs/run",
)
