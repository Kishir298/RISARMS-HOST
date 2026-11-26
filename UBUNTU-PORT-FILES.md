# Ubuntu 24.04 candidate integration record

This file records the additive Ubuntu Server 24.04 LTS x86_64/systemd
candidate merged from `RISARMS-Ubuntu-Port-Candidate.zip` into the
RISARMS-HOST checkout. The source archive SHA-256 is
`313F86AA5FE52C00D1A0FF8CD06C424A04342C3F3374E7C2A12408071C8B5023`
and the base commit is
`337e36a9bd26c283b687b8fa6585e041c1ca809e`.

Read `deployment/ubuntu/README.md` for build, install, operations and
validation steps. The installer expects an assembled bundle, not an
unassembled umbrella checkout. Target: fresh Ubuntu Server 24.04 LTS
x86_64/systemd. Candidate, not production validated. Main application code
and the existing Void releases are unchanged.

## Added paths

| Path | Purpose |
|---|---|
| `deployment/ubuntu/README.md` | Candidate build/install/operations guide |
| `deployment/ubuntu/backup.sh` | Root-only backup with service pause |
| `deployment/ubuntu/configure.py` | First-time config without key rotation |
| `deployment/ubuntu/doctor.sh` | Static/runtime diagnostics |
| `deployment/ubuntu/install.sh` | Ubuntu installer with fixed safe paths |
| `deployment/ubuntu/lib.sh` | Shared Ubuntu helpers |
| `deployment/ubuntu/portal.caddy` | Caddy portal site |
| `deployment/ubuntu/restore.sh` | Validated restore path |
| `deployment/ubuntu/risarms-core.service` | Hardened CORE unit |
| `deployment/ubuntu/risarms-rescs.service` | Hardened RESCS unit |
| `deployment/ubuntu/rollback.sh` | Versioned venv rollback |
| `deployment/ubuntu/upgrade.sh` | Newer-version upgrade guard |
| `deployment/ubuntu/validate-backup.py` | Backup member/path validator |
| `risarms_host/ubuntu_release.py` | Ubuntu candidate archive builder |
| `.github/workflows/ubuntu-candidate.yml` | Static candidate CI workflow |
| `tests/test_ubuntu_port.py` | Candidate behavior/invariant tests |

## Integration fixes

- Python 3.10 compatibility: `ubuntu_release.py` now has a stdlib TOML
  version fallback instead of an unconditional `tomllib` import.
- `upgrade.sh` refuses same-version upgrades instead of claiming the
  installer will reinstall them.
- `install.sh` no longer requires unused `systemd-analyze`.
- Backups now include `/etc/caddy/Caddyfile` and the backup validator
  accepts that exact path.
- `.gitattributes` forces LF endings for all `deployment/ubuntu/**` files.
- Ubuntu shell scripts are stored with git mode `100755`.

## Validation status

Static tests, shell syntax checks, archive reproducibility and manifest
checks are intended to run in CI. Booted Ubuntu install, systemd service
startup/reboot, Caddy TLS, backup/restore, upgrade/rollback and physical
hardware validation remain pending. No GitHub commit, push, release or
host installation was performed while preparing this record.
