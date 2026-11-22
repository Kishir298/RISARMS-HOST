# RISARMS-HOST — umbrella for the RISARMS workspace

`RISARMS-HOST` is the **umbrella** repository of the RISARMS workspace. It owns
deployment (Void Linux and Raspberry Pi installers, Caddy, nftables, runit
services), vendored service sources, release manifests, validation evidence and
the `risarms-host` operator CLI. It ships no CORE runtime code — every component
lives in a sibling repository:

| Component | Repository |
| --- | --- |
| CORE host runtime (server) | `CORE-HOST` |
| CORE external-device client | `CORE-CLIENT` |
| Resource-sharing service | `RESCS` |
| TIVISS host | `TIVISS-HOST` |
| TIVISS client library | `TIVISS-CLIENT` |
| Desktop application | `RISARMS-ui` |
| Agent Command and Context service | `ASCS` |
| Agent Internet service | `ASIS` |
| Documentation | `RISARMS-DOCS` |

The release bundle assembled by CI keeps the historical layout: the archive root
contains `CORE-HOST/`, `CORE-CLIENT/`, `services/`, `deployment/` and
`compatibility.json`, so `deployment/void/install.sh` keeps working unchanged.

## Umbrella CLI

```bash
pip install -e ".[test]"
risarms-host version                  # umbrella + compatibility.json version
risarms-host doctor --root .          # manifest, version lock-step, deployment files
risarms-host components --root ..     # sibling component checkouts
risarms-host stage --root . --dest build/src   # pinned components + umbrella assets
risarms-host bundle --root build/src --out release --tar
risarms-host provenance --root . --version 0.6.0 --channel beta \
  --artifact release/CORE-Server-0.6.0-void-x86_64.tar.gz \
  --out release/provenance.json
```

`risarms-host` is stdlib-only and requires Python 3.10 or newer. `doctor` exits
non-zero when a check fails.

## Repository contents

- `deployment/` — Void Linux installer, doctor/backup/restore/upgrade/rollback,
  Caddy and nftables configuration, runit service definitions; Raspberry Pi
  installer retained for provenance.
- `services/` — vendored sources of the ASCS, ASIS, RESCS and TIVISS-HOST
  services with the git baselines recorded in `services/SOURCE-PROVENANCE.json`.
- `install/` — historical wheel artifacts of earlier releases.
- `validation/` — recorded validation logs and `RELEASE-VALIDATION.json`.
- `scripts/` — PyInstaller entry points used by `BUILDING.md`.
- `compatibility.json` — compatibility source of truth for releases.
- `components.lock.json` — exact commit of every component included in a server
  release; `risarms-host stage` materialises these pins.
- `.github/workflows/release.yml` — server release orchestration (staging,
  assembly, install verification, checksums, provenance, SBOM, draft release).
- `RELEASE-MANIFEST.json` — frozen per-file SHA-256 record of the 0.5.0 release
  (historical evidence; it is not regenerated for later releases).

## Server release 0.6.0 (Void Linux x86_64)

CORE 0.6.0 is the RISARMS server release for **Void Linux x86_64 with glibc and runit**. CORE-HOST and RESCS run as separate unprivileged services behind Caddy. The browser portal remains the primary interface; RISARMS-ui 0.6.0 is the separate desktop application.

**Status: beta, release-candidate source.** The installer and service assets exist, but installation, reboot, rollback, storage-failure, and runtime validation on real Void hardware remain pending. Do not describe this release as hardware-certified.

### Target hardware

- HP 14-dq1037wm (`7PR51UA#ABA`), x86_64, UEFI, internal storage.
- Void Linux with glibc and runit.
- At least 5 GiB free when installing; override only after checking the disk with `RISARMS_MIN_FREE_GIB`.
- Installed RAM is unverified (an earlier report indicated 4 GB). 8 GB is the recommended minimum for the server and small local models. The planned 2 x 8 GB Samsung DDR4-2666 SO-DIMM upgrade to 16 GB is **not installed or verified** yet.
- Raspberry Pi, ARM64, systemd, Windows-host, and macOS-host server deployments are **historical or unsupported** for this release.

### Install

Review the scripts before running them. The installer does not partition disks, format storage, enable services, or start the portal.

```bash
sudo xbps-install -S python3 python3-pip caddy runit-void nftables elogind
tar -xzf CORE-Server-0.6.0-void-x86_64.tar.gz
cd CORE-Server-0.6.0-void-x86_64
sudo ./deployment/void/install.sh
```

The default public origin is `https://core.local`. Set a different origin only with a fully qualified HTTPS address:

```bash
sudo RISARMS_PUBLIC_ORIGIN=https://core.example.test ./deployment/void/install.sh
```

Review these files before enabling anything:

- `/etc/risarms/core.env`
- `/etc/risarms/rescs.env`
- `/etc/risarms/gateway.json`
- `/etc/caddy/risarms/portal.caddy`
- `/etc/nftables.d/risarms.nft`

Enable the services explicitly:

```bash
sudo ln -s /etc/sv/risarms-rescs /var/service/
sudo ln -s /etc/sv/risarms-core /var/service/
sudo ln -s /etc/sv/caddy /var/service/
sudo sv status risarms-core risarms-rescs caddy
sudo risarms-doctor
```

The first-owner setup key is written to the CORE log:

```bash
sudo tail -n 50 /var/log/risarms/core/current
```

Trust Caddy's local CA on the client before opening `https://core.local`. Copy only the public root certificate, never the private key.

### Operations

```bash
sudo risarms-backup
sudo risarms-restore --yes /var/lib/risarms/backups/risarms-<stamp>.tar.gz
sudo risarms-upgrade /path/to/new/CORE-Server-<version>-void-x86_64
sudo risarms-rollback
sudo risarms-doctor
```

- Backups include CORE data, RESCS data, frontend files, `/etc/risarms`, and RISARMS Caddy/nftables/elogind/runit configuration. They contain secrets and are written with mode `0600`.
- Backups are not encrypted by the installer. Store copies only on media with equivalent protection.
- Upgrade builds versioned virtual environments and switches stable symlinks. Rollback switches those symlinks back; database and configuration rollback use `risarms-restore`.
- RESCS uses SQLite under `/var/lib/risarms/rescs/database`. Back up CORE and RESCS together.
- CORE listens on loopback ports 8780 and 8781; RESCS listens on 8081. Caddy exposes HTTPS and the portal.
- Caddy uses its internal CA. The nftables include is validated but not loaded automatically.

### Release assets

- `CORE-Server-<version>-void-x86_64.tar.gz`: source tree, Void installer, runit services, backup/restore/upgrade/rollback/diagnostics scripts.
- `SHA256SUMS`: checksums for the server archive and SBOM.
- `sbom-<name>.cdx.json`: CycloneDX SBOM.
- GitHub releases are created as **drafts** first. No tag, release, or server update signature is published by the workflow automatically.

### Compatibility and security

- CORE package version: `0.6.0`.
- CORE protocol: `0.4.0`; supported wire versions are `0.3.0` and `0.4.0`.
- RESCS bundled version: `0.4.0`.
- RISARMS-ui desktop target: `0.6.0`, released separately.
- The compatibility source of truth is `compatibility.json`.
- Panic, restart, and uninstall behavior are documented in the RISARMS-DOCS deployment guide. Removing `/var/lib/risarms` destroys data.
- No CORE server update signature is implemented in this release. Do not claim signed server updates.

### Historical deployments

`deployment/pi`, `deployment/linux`, Pi setup guides, `VALIDATION.md`, and systemd-oriented instructions are retained for provenance. They are not current CORE 0.6.0 release targets. See RISARMS-DOCS for migration and validation status.
