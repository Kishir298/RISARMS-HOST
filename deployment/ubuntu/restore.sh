#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ -r $SCRIPT_DIR/lib.sh ]]; then
    # shellcheck source=lib.sh
    . "$SCRIPT_DIR/lib.sh"
else
    # shellcheck source=/dev/null
    . /usr/local/lib/risarms/common.sh
fi

risarms_require_root
risarms_require_ubuntu
exec 9>/run/lock/risarms-maintenance.lock
flock -n 9 || risarms_die "Another maintenance operation is running."
risarms_require_commands tar gzip python3

if [[ $# -gt 0 && $1 == "--yes" ]]; then
    shift
    ASSUME_YES=1
else
    ASSUME_YES=0
fi
ARCHIVE=${1:-}
if [[ -z $ARCHIVE ]]; then
    ARCHIVE=$(find "$RISARMS_DATA/backups" -maxdepth 1 -name 'risarms-*.tar.gz' -print 2>/dev/null | sort | tail -n 1)
fi
[[ -n $ARCHIVE && -f $ARCHIVE ]] || risarms_die "Usage: risarms-restore [--yes] <backup.tar.gz>"
ARCHIVE=$(readlink -f "$ARCHIVE")

if [[ -f $ARCHIVE.sha256 ]]; then
    (cd "$(dirname "$ARCHIVE")" && sha256sum -c "$(basename "$ARCHIVE").sha256")
fi

# Validate every member type and path before a privileged extraction.
python3 /usr/local/lib/risarms/validate-backup.py "$ARCHIVE"
if (( ASSUME_YES == 0 )); then
    printf 'Restore %s over %s? [y/N] ' "$ARCHIVE" "$RISARMS_DATA"
    read -r answer
    [[ $answer == y || $answer == Y ]] || risarms_die "Restore cancelled."
fi

CORE_WAS_UP=0
RESCS_WAS_UP=0
CADDY_WAS_UP=0
risarms_service_up risarms-core && CORE_WAS_UP=1
risarms_service_up risarms-rescs && RESCS_WAS_UP=1
risarms_service_up caddy && CADDY_WAS_UP=1
restore_services() {
    if (( RESCS_WAS_UP == 1 )); then systemctl start risarms-rescs 2>/dev/null || true; fi
    if (( CORE_WAS_UP == 1 )); then systemctl start risarms-core 2>/dev/null || true; fi
}
trap restore_services EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if (( CORE_WAS_UP == 1 )); then systemctl stop risarms-core; fi
if (( RESCS_WAS_UP == 1 )); then systemctl stop risarms-rescs; fi


tar -C / --no-same-owner -xzpf "$ARCHIVE"
systemctl daemon-reload
chown -R risarms:risarms \
    "$RISARMS_DATA/core" "$RISARMS_DATA/rescs" "$RISARMS_LOG" 2>/dev/null || true
chmod 0600 "$RISARMS_ETC"/*.env "$RISARMS_ETC/gateway.json" 2>/dev/null || true
if [[ -f $RISARMS_DATA/core/gateway.json ]]; then
    chown risarms:risarms "$RISARMS_DATA/core/gateway.json"
    chmod 0600 "$RISARMS_DATA/core/gateway.json"
fi
if (( CADDY_WAS_UP == 1 )); then systemctl restart caddy 2>/dev/null || true; fi
printf 'Restored %s\n' "$ARCHIVE"
