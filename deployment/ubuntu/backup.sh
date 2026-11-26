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
umask 077
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
DEST=${RISARMS_BACKUP_DIR:-$RISARMS_DATA/backups}
ARCHIVE="$DEST/risarms-$STAMP.tar.gz"
RETENTION=${RISARMS_BACKUP_RETENTION_DAYS:-14}
[[ $RETENTION =~ ^[0-9]+$ ]] || risarms_die "RISARMS_BACKUP_RETENTION_DAYS must be numeric."
install -d -m 0700 -o risarms -g risarms "$DEST"

CORE_WAS_UP=0
RESCS_WAS_UP=0
risarms_service_up risarms-core && CORE_WAS_UP=1
risarms_service_up risarms-rescs && RESCS_WAS_UP=1
restore_services() {
    if (( RESCS_WAS_UP == 1 )); then systemctl start risarms-rescs 2>/dev/null || true; fi
    if (( CORE_WAS_UP == 1 )); then systemctl start risarms-core 2>/dev/null || true; fi
}
trap restore_services EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
if (( CORE_WAS_UP == 1 )); then systemctl stop risarms-core; fi
if (( RESCS_WAS_UP == 1 )); then systemctl stop risarms-rescs; fi


paths=(etc/risarms var/lib/risarms/core var/lib/risarms/rescs var/lib/risarms/frontend var/lib/risarms/install-state)
for optional in etc/caddy/Caddyfile etc/caddy/risarms etc/systemd/system/risarms-core.service etc/systemd/system/risarms-rescs.service etc/systemd/logind.conf.d/risarms.conf; do
    if [[ -e /$optional ]]; then paths+=("$optional"); fi
done
tar -C / --one-file-system -czf "$ARCHIVE" "${paths[@]}"
chmod 0600 "$ARCHIVE"
if command -v sha256sum >/dev/null 2>&1; then
    (cd "$DEST" && sha256sum "$(basename "$ARCHIVE")" > "$(basename "$ARCHIVE").sha256")
    chmod 0600 "$ARCHIVE.sha256"
fi
find "$DEST" -maxdepth 1 -name 'risarms-*.tar.gz' -mtime +"$RETENTION" -delete
find "$DEST" -maxdepth 1 -name 'risarms-*.tar.gz.sha256' -mtime +"$RETENTION" -delete
printf 'Backup written to %s\n' "$ARCHIVE"
