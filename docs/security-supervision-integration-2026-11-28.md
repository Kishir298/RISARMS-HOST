# Security, approval, quota and supervision integration (2026-11-28)

This umbrella release target keeps the Void x86_64 **runit** deployment and the
**Ubuntu Server 24.04 x86_64 systemd candidate**. CORE coordinates application
state; the OS service manager supervises processes. Nothing here adds a
competing restart loop: the new `core.health.contract.FailureTracker` is
bounded and advisory, and the units remain the only process supervisors.

## What changed downstream

| Component | Change | Deployment impact |
| --- | --- | --- |
| CORE-HOST | Pending device enrollment/approval, `GET /api/security`, health/resource/alert contract | No unit change. Existing databases migrate additively (`devices.status` defaults to `approved`) |
| TIVISS-CLIENT | Device security client 0.2.0 | Client-side only; not part of the server archive |
| RESCS | `rescs.quota`, `rescs.provisioning` | No unit change; provisioning is additive under the storage directory |
| ASIS | Optional CORE-mediated memory sync | No unit change; disabled without configuration |
| ASCS | Permission modes | Local tool only; not a server service |
| RISARMS-ui | Security page replaces the TIVISS chat surface | Desktop targets unchanged (Windows/macOS/Linux) |

## Compatibility

`compatibility.json` now advertises the capabilities
`device_approval_v1`, `security_status_v1`, `security_events_v1`,
`supervision_contract_v1`, `quota_policy_v1`, `memory_sync_v1` and
`permission_modes_v1`. All wire contracts are additive `schema_version: 1`
documents; an unknown schema version is rejected by clients.

## Component pins — deliberately unchanged

`components.lock.json` was **not** rewritten. The pinned commits predate this
work, and pinning the new local commits before they have been pushed (and
before a passing CI run exists for them) would require inventing or guessing a
hash, which is forbidden.

To update pins after an authorized push:

1. Push the changed component repositories.
2. Wait for their CI to pass.
3. Set each `revision` in `components.lock.json` to the pushed 40-character
   commit.
4. Re-run `risarms-host stage`, the install assertions and the archive checks.

## Validation status

- Static/unit checks: see `RISARMS-DOCS/development/requirements-checklist-2026-11-28.md`.
- Container/booted validation: **not performed** in this session (no container
  runtime or boot environment).
- Artifacts remain **VALIDATION-ONLY**; no update-signing keys are configured
  and no release was published.
