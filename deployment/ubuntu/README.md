# Ubuntu Server port candidate

Target: a fresh Ubuntu Server **24.04 LTS x86_64** installation with systemd.
This port has not been installed or boot-tested on Ubuntu. Do not label it a
validated release. The default Void manifest and workflow are intentionally
preserved; the separate builder writes Ubuntu metadata into its own archive.
No application repositories need replacement.

## Integration status

These files are already merged into this `RISARMS-HOST` checkout at the paths
recorded in `UBUNTU-PORT-FILES.md` (repository root). No existing file needed
replacement at the checked base commit.

## Build on your development computer (Python 3.10+ and Git)

From RISARMS-HOST:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
.venv/bin/python -m risarms_host.ubuntu_release --out build/ubuntu
```

Alternatively commit/push under your existing permissions, then manually run
**Ubuntu server candidate** in GitHub Actions. That workflow builds artifacts;
it neither installs on the runner nor creates a release. No signing claim.
The SBOM describes the build environment, not all transitive runtime packages.
Python dependencies are fetched on install; this is not an offline installer.

## Install candidate on a disposable Ubuntu VM first

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip caddy nftables ca-certificates
sha256sum -c SHA256SUMS
tar -xzf CORE-Server-0.6.0-ubuntu24.04-x86_64.tar.gz
cd CORE-Server-0.6.0-ubuntu24.04-x86_64
sudo bash deployment/ubuntu/install.sh
```

APT may start its packaged Caddy service. The RISARMS installer writes units
but does not enable them automatically. Review `/etc/risarms/*.env` and
`/etc/caddy/risarms/portal.caddy`, then:

```sh
sudo systemctl enable --now risarms-rescs risarms-core caddy
sudo systemctl restart caddy
sudo systemctl status risarms-rescs risarms-core caddy
sudo journalctl -u risarms-core -f
sudo risarms-doctor
```

First-owner setup messages are in CORE's journal. Do not share logs containing
setup keys. CORE/RESCS bind loopback; Caddy exposes HTTPS. `core.local` must
resolve to the server on every client, and clients must trust the public
Caddy root CA certificate (never copy its private key).

Firewall setup is manual: preserve SSH access before enabling your existing
UFW/nftables policy and allow the intended HTTPS clients. This installer does
not load firewall rules, repartition drives or modify lid-close policy.
If desired, separately configure `/etc/systemd/logind.conf.d/` for laptop
lid behavior after checking the installed system's logind documentation.

## Operations

```sh
sudo risarms-backup
sudo risarms-restore --yes /var/lib/risarms/backups/risarms-TIMESTAMP.tar.gz
sudo risarms-upgrade /path/to/extracted-NEW-version
sudo risarms-rollback
```

Backups contain secrets and are mode 0600, not encrypted. Only restore trusted
Ubuntu-port backups on the same deployment. Restore merges files, and does not
remove files absent from the archive. Binary rollback requires the old venvs
still on disk; it does not reverse database/schema changes. A failed upgrade
may require restoring configuration/data from your pre-upgrade backup.
Take a backup before every upgrade. Reinstalling the same version is refused
so an existing venv is never deleted beneath a running service.

This candidate shares the baseline `risarms` Unix account between CORE and
RESCS; existing application-level user authorization remains responsible for
user isolation. Do not claim this prevents a machine administrator from
accessing plaintext data.

## Required validation before release

On a disposable booted 24.04 VM: fresh install, service startup/reboot,
first-owner login, two-user file/message isolation, CORE↔RESCS, Caddy TLS,
firewall/SSH reachability, backup/restore, newer-version upgrade/rollback,
low-space refusal and failure recovery. Then repeat on the HP reference
machine. Windows/macOS desktop support is unchanged by this deployment port.

After validation, create an explicitly marked draft prerelease from the
verified artifact set. Use an Ubuntu-specific tag (for example
`ubuntu-v0.6.0-beta.1`) so the existing Void `v*` workflow is not triggered.
With gh already authenticated, create the draft from the verified commit:

```sh
gh release create ubuntu-v0.6.0-beta.1 \
  --repo Kishir298/RISARMS-HOST --target VERIFIED_FULL_COMMIT_SHA \
  --draft --prerelease --title 'CORE 0.6.0 Ubuntu 24.04 beta 1' \
  --notes-file release-notes.md \
  build/ubuntu/CORE-Server-0.6.0-ubuntu24.04-x86_64.tar.gz \
  build/ubuntu/SHA256SUMS build/ubuntu/ubuntu-provenance.json
```

Use the exact downloads from the validated CI run; do not silently rebuild.
Review the draft in GitHub before publishing. The example assumes you have
written release-notes.md with actual evidence and limitations. No draft or
release was created while preparing this port.
