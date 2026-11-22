import hashlib
import json

from risarms_host import provenance, revisions
from risarms_host.layout import BUNDLE_COMPONENT_PATHS


def make_pinned():
    return [
        revisions.PinnedComponent(
            name=name,
            repository=f"https://github.com/Kishir298/{name.upper()}.git",
            revision="c" * 40,
            path=path,
        )
        for name, path in sorted(BUNDLE_COMPONENT_PATHS.items())
    ]


def test_statement_records_artifact_digests(tmp_path):
    artifact = tmp_path / "CORE-Server-0.6.0-void-x86_64.tar.gz"
    artifact.write_bytes(b"archive")
    data = provenance.statement(
        make_pinned(),
        version="0.6.0",
        channel="beta",
        artifacts=[artifact],
        source_uri="https://github.com/Kishir298/RISARMS-HOST",
        workflow_ref="refs/tags/v0.6.0-beta.1",
        run_id="1234",
        generated_at="2026-11-22T00:00:00Z",
    )
    assert data["_type"] == provenance.STATEMENT_TYPE
    assert data["predicateType"] == provenance.PREDICATE_TYPE
    assert data["subject"] == [
        {
            "name": artifact.name,
            "digest": {"sha256": hashlib.sha256(b"archive").hexdigest()},
        }
    ]
    predicate = data["predicate"]
    assert predicate["buildDefinition"]["externalParameters"]["version"] == "0.6.0"
    assert predicate["buildDefinition"]["externalParameters"]["channel"] == "beta"
    revisions_recorded = {
        name: entry["revision"]
        for name, entry in predicate["buildDefinition"]["externalParameters"][
            "components"
        ].items()
    }
    assert revisions_recorded == {name: "c" * 40 for name in BUNDLE_COMPONENT_PATHS}
    assert predicate["runDetails"]["metadata"]["invocationId"] == "1234"
    assert len(predicate["buildDefinition"]["resolvedDependencies"]) == len(
        BUNDLE_COMPONENT_PATHS
    )


def test_statement_timestamp_uses_source_date_epoch(tmp_path, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    artifact = tmp_path / "a.tar.gz"
    artifact.write_bytes(b"x")
    data = provenance.statement(
        make_pinned(), version="0.6.0", channel="stable", artifacts=[artifact]
    )
    assert data["predicate"]["runDetails"]["metadata"]["startedOn"] == (
        "2023-11-14T22:13:20Z"
    )
    assert data["predicate"]["buildDefinition"]["internalParameters"] == {
        "sourceDateEpoch": 1700000000
    }


def test_write_is_stable_json(tmp_path):
    artifact = tmp_path / "a.tar.gz"
    artifact.write_bytes(b"x")
    data = provenance.statement(
        make_pinned(),
        version="0.6.0",
        channel="stable",
        artifacts=[artifact],
        generated_at="2026-11-22T00:00:00Z",
    )
    target = provenance.write(tmp_path / "nested" / "provenance.json", data)
    assert json.loads(target.read_text(encoding="utf-8")) == data
    assert target.read_text(encoding="utf-8").endswith("\n")
