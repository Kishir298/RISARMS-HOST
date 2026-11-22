"""Unsigned build provenance for an assembled CORE server release.

The statement follows the SLSA v1 shape (``Statement`` + ``provenance/v1``
predicate) but is **not signed** and is not an attestation. It records the
exact component commits, workflow identity and artifact digests so a reviewer
can reproduce and verify the archive by hand.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

BUILD_TYPE = "https://github.com/Kishir298/RISARMS-HOST/buildtypes/components-lock/v1"
STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_TYPE = "https://slsa.dev/provenance/v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamp() -> str:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "")
    if raw.isdigit():
        return datetime.fromtimestamp(int(raw), tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def statement(
    pinned,
    *,
    version: str,
    channel: str,
    artifacts: list[Path],
    source_uri: str = "",
    workflow_ref: str = "",
    run_id: str = "",
    generated_at: str | None = None,
) -> dict:
    """Build the provenance statement for ``artifacts``."""
    moment = generated_at or _timestamp()
    subjects = [
        {"name": Path(item).name, "digest": {"sha256": sha256(Path(item))}}
        for item in artifacts
    ]
    components = {
        component.name: {
            "repository": component.repository,
            "revision": component.revision,
            "path": component.path,
        }
        for component in pinned
    }
    return {
        "_type": STATEMENT_TYPE,
        "subject": subjects,
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "buildDefinition": {
                "buildType": BUILD_TYPE,
                "externalParameters": {
                    "version": version,
                    "channel": channel,
                    "source": source_uri,
                    "components": components,
                },
                "internalParameters": {"sourceDateEpoch": _source_date_epoch()},
                "resolvedDependencies": [
                    {"uri": component.repository, "digest": {"gitCommit": component.revision}}
                    for component in pinned
                ],
            },
            "runDetails": {
                "builder": {"id": "https://github.com/Kishir298/RISARMS-HOST/actions"},
                "metadata": {
                    "invocationId": run_id,
                    "startedOn": moment,
                    "finishedOn": moment,
                },
                "byproducts": [],
            },
        },
    }


def _source_date_epoch() -> int:
    raw = os.environ.get("SOURCE_DATE_EPOCH", "")
    return int(raw) if raw.isdigit() else 0


def write(path: Path, data: dict) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
