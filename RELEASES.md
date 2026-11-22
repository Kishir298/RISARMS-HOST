# CORE Server Releases

CORE follows independent semantic versioning (`MAJOR.MINOR.PATCH`). Server
releases are built and published from **this repository** (`RISARMS-HOST`).
The CORE host runtime, the CORE client and the services are separate
repositories; RISARMS-HOST owns umbrella deployment, bundle assembly and
server release orchestration.

The version is declared in `pyproject.toml`, `risarms_host/__init__.py`,
`compatibility.json` and `components.lock.json`; the release workflow refuses
to build if they disagree.

The **wire protocol** has its own version (`0.4.0` in
`CORE-HOST/core/communication/protocol.py`). It is intentionally decoupled
from the package version, so a package release does not silently change the
protocol.

## Target

CORE 0.6.0 server releases target **Void Linux x86_64 glibc with runit** only.
The release archive is a source tree plus the Void installer and deployment
assets; it is not a portable server binary. Cross-platform development tests do
not imply additional supported server release targets.

## Pinned components

`components.lock.json` pins every component to an exact 40-character commit:

| Component | Bundle path |
| --- | --- |
| `core-host` | `CORE-HOST/` |
| `core-client` | `CORE-CLIENT/` |
| `rescs` | `services/RESCS/` |
| `ascs` | `services/ASCS/` |
| `asis` | `services/ASIS/` |
| `tiviss-host` | `services/TIVISS-HOST/` |

`risarms-host stage` materialises those pins and copies the umbrella-owned
deployment assets, `compatibility.json` and the lock itself. `risarms-host
bundle` then assembles the historical layout, so `deployment/void/install.sh`
keeps working unchanged.

## Channels

| Channel | Trigger | GitHub Release |
| --- | --- | --- |
| Stable | tag `vX.Y.Z` | draft release, not prerelease; requires manifest channel `stable` |
| Beta | tag `vX.Y.Z-beta.N` | draft prerelease |
| Development | `workflow_dispatch` | artifacts only, no Release |

The manifest currently declares `release_channel: beta`, so the workflow
rejects a stable tag until that field is changed intentionally. Releases are
created with `--draft`; nothing is published automatically.

## Artifacts

- `CORE-Server-<version>-void-x86_64.tar.gz`
- `sbom-CORE-Server-<version>-void-x86_64.cdx.json` (CycloneDX JSON)
- `provenance.json` (unsigned in-toto statement, SLSA v1 shape)
- `SHA256SUMS`

The archive contains `CORE-HOST/`, `CORE-CLIENT/`, `services/`, `deployment/`,
`compatibility.json`, `components.lock.json` and `INSTALL.txt`. Checksums,
SBOM and provenance are not nested inside it.

Archives are byte-identical when the same staged tree is assembled twice: entry
order is sorted, ownership is normalised and timestamps come from
`SOURCE_DATE_EPOCH`. The workflow re-assembles and compares before uploading.

## Process

1. Update the version in `pyproject.toml`, `risarms_host/__init__.py`,
   `compatibility.json`, `components.lock.json` and `CHANGELOG.md`; set
   `release_channel` deliberately.
2. Refresh each pin in `components.lock.json` to the release commit of that
   component.
3. Run `python -m pytest -q` and `ruff check --select E9,F,I risarms_host tests`.
4. Commit, then create and push an annotated tag: `git tag -a vX.Y.Z-beta.N -m "CORE X.Y.Z-beta.N"`.
5. The workflow validates tag/version/channel/manifest agreement, stages the
   pinned components, assembles and re-assembles the archive, verifies
   installation with the shipped Void installer in a `void-glibc-full`
   container, writes checksums, provenance and the SBOM, and creates a draft.
6. A human reviews the draft, records the pending hardware validation, and
   publishes it only when authorized.

Never create a tag or release as part of an ordinary commit/push.

## Validation levels

| Level | Meaning |
| --- | --- |
| Static | Released tests and lint pass. |
| Assembly | Pinned components stage, the archive is complete and reproducible. |
| Container install | The shipped installer completes in Void x86_64 glibc and the installed venvs import. This is not hardware certification. |
| Hardware | Physical HP 14: install, reboot persistence, runit, Caddy/TLS, firewall, storage failure, backup/restore, upgrade/rollback. **Not yet performed.** |

Do not describe a release as hardware-certified or as having a signed server
updater.

## Signing

CORE server archives are not code-signed and CORE has no signed server updater.
`provenance.json` is unsigned; it records the pinned commits, workflow identity
and artifact digests so a reviewer can verify a build by hand. This is
unrelated to the RISARMS-ui desktop update signature and to Apple/Windows OS
code signing, both of which belong to the desktop release process.
