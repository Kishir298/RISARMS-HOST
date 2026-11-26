#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SOURCE=$(cd -- "$SCRIPT_DIR/../.." && pwd)
# shellcheck source=lib.sh
. "$SCRIPT_DIR/lib.sh"

risarms_require_root
risarms_require_ubuntu
risarms_require_commands python3 caddy systemctl useradd install df tar gzip readlink sed ln mv cp find flock
python3 -c 'import venv, ensurepip' || risarms_die "Install python3-venv first."
exec 9>/run/lock/risarms-maintenance.lock
flock -n 9 || risarms_die "Another installer is running."
if [[ -e /etc/sv/risarms-core ]]; then
    risarms_die "Existing Void deployment found. Migrate with a separate backup/restore procedure."
fi

VERSION=$(risarms_version_from_source "$SOURCE")
[[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || risarms_die "Invalid release version."
[[ ! -e $RISARMS_APP/venvs/$VERSION ]] || risarms_die "Version $VERSION already exists; use a new version for upgrade."
# This port keeps fixed service paths; do not accept conflicting overrides.
[[ $RISARMS_APP == /opt/risarms && $RISARMS_ETC == /etc/risarms && $RISARMS_DATA == /var/lib/risarms ]] || risarms_die "Custom install paths are not supported."
PREVIOUS_VERSION=$(risarms_current_version 2>/dev/null || true)
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ORIGIN=${RISARMS_PUBLIC_ORIGIN:-}
if [[ -z $ORIGIN && -r $RISARMS_ETC/core.env ]]; then
    ORIGIN=$(sed -n 's/^CORE_PUBLIC_ORIGIN=//p' "$RISARMS_ETC/core.env" | head -n 1)
fi
ORIGIN=${ORIGIN:-https://core.local}
[[ $ORIGIN =~ ^https://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]{1,5})?$ ]] ||
    risarms_die "RISARMS_PUBLIC_ORIGIN must be an https origin without a path or trailing slash."

CORE_WAS_UP=0
RESCS_WAS_UP=0
CADDY_WAS_UP=0
risarms_service_up risarms-core && CORE_WAS_UP=1
risarms_service_up risarms-rescs && RESCS_WAS_UP=1
risarms_service_up caddy && CADDY_WAS_UP=1
PREVIOUS_CORE_TARGET=$(readlink -f "$RISARMS_APP/core-venv" 2>/dev/null || true)
PREVIOUS_RESCS_TARGET=$(readlink -f "$RISARMS_APP/rescs-venv" 2>/dev/null || true)

restore_previous_links() {
    local status=$?
    if (( status != 0 )); then
        [[ -n $PREVIOUS_CORE_TARGET ]] && risarms_atomic_link "$PREVIOUS_CORE_TARGET" "$RISARMS_APP/core-venv" || true
        [[ -n $PREVIOUS_RESCS_TARGET ]] && risarms_atomic_link "$PREVIOUS_RESCS_TARGET" "$RISARMS_APP/rescs-venv" || true
        if (( RESCS_WAS_UP )); then systemctl restart risarms-rescs || true; fi
        if (( CORE_WAS_UP )); then systemctl restart risarms-core || true; fi
    fi
    exit "$status"
}
trap restore_previous_links EXIT

if ! id risarms >/dev/null 2>&1; then
    useradd --system --user-group --home-dir "$RISARMS_DATA" --shell /usr/sbin/nologin risarms
fi

install -d -m 0755 "$RISARMS_APP" "$RISARMS_APP/venvs" "$RISARMS_ETC" "$RISARMS_LOG"
install -d -m 0711 -o root -g root "$RISARMS_DATA"
install -d -m 0700 -o risarms -g risarms "$RISARMS_DATA/core"
install -d -m 0700 -o risarms -g risarms \
    "$RISARMS_DATA/rescs" "$RISARMS_DATA/rescs/database" \
    "$RISARMS_DATA/rescs/files" "$RISARMS_DATA/rescs/tmp" "$RISARMS_DATA/rescs/trash"
install -d -m 0700 -o risarms -g risarms \
    "$RISARMS_LOG/core" "$RISARMS_LOG/rescs" "$RISARMS_DATA/backups" "$RISARMS_STATE"
install -d -m 0700 -o risarms -g risarms /run/risarms-inference
install -d -m 0755 "$RISARMS_DATA/frontend"

risarms_check_free_space "$RISARMS_DATA"
install -m 0644 "$SOURCE/CORE-HOST/core/web/portal.html" "$RISARMS_DATA/frontend/index.html"

build_venv() {
    local name=$1
    local source=$2
    local target
    target=$(risarms_venv_path "$name" "$VERSION")
    local staging="$RISARMS_APP/venvs/$VERSION/.$name.build.$$"
    install -d -m 0755 "$RISARMS_APP/venvs/$VERSION"
    rm -rf "$staging"
    python3 -m venv "$staging"
    "$staging/bin/python" -m pip install "$source"
    "$staging/bin/python" -c "import $3; print('$name ready')"
    mv "$staging" "$target"
    # pip writes console scripts whose shebang is the absolute interpreter path
    # of the build directory. After the rename those paths no longer exist, so
    # runit would fail with "file does not exist" even though the script does.
    for script in "$target"/bin/*; do
        [[ -f $script ]] || continue
        if head -n 1 "$script" | grep -qF "$staging/bin/python"; then
            sed -i "1s|$staging|$target|" "$script"
        fi
    done
}

risarms_snapshot_install "$STAMP" >/dev/null
build_venv core "$SOURCE/CORE-HOST" core.version
build_venv rescs "$SOURCE/services/RESCS" rescs

for name in core rescs; do
    link="$RISARMS_APP/$name-venv"
    if [[ -e $link && ! -L $link ]]; then
        mv "$link" "$RISARMS_APP/legacy-$name-venv-$STAMP"
    fi
    risarms_atomic_link "venvs/$VERSION/$name" "$link"
done

if [[ ! -f $RISARMS_ETC/core.env && ! -f $RISARMS_ETC/rescs.env ]]; then
    python3 "$SCRIPT_DIR/configure.py" --origin "$ORIGIN"
elif [[ ! -f $RISARMS_ETC/core.env || ! -f $RISARMS_ETC/rescs.env ]]; then
    risarms_die "Only one environment file exists; repair configuration without regenerating keys."
else
    python3 "$SCRIPT_DIR/configure.py" --reconcile --origin "$ORIGIN"
fi

chown -R risarms:risarms "$RISARMS_DATA/core" "$RISARMS_DATA/rescs" "$RISARMS_LOG"
if [[ -f $RISARMS_DATA/core/gateway.json ]]; then
    chown risarms:risarms "$RISARMS_DATA/core/gateway.json"
fi
chmod 0600 "$RISARMS_ETC"/*.env "$RISARMS_ETC/gateway.json" "$RISARMS_DATA/core/gateway.json"

install -m 0644 "$SCRIPT_DIR/risarms-core.service" /etc/systemd/system/risarms-core.service
install -m 0644 "$SCRIPT_DIR/risarms-rescs.service" /etc/systemd/system/risarms-rescs.service
systemctl daemon-reload
install -d -m 0755 /etc/caddy/risarms
sed "s|https://core.local|$ORIGIN|g" "$SCRIPT_DIR/portal.caddy" \
    > /etc/caddy/risarms/portal.caddy
chmod 0644 /etc/caddy/risarms/portal.caddy
if [[ ! -f /etc/caddy/Caddyfile ]]; then
    echo 'import /etc/caddy/risarms/*.caddy' > /etc/caddy/Caddyfile
elif ! grep -qxF 'import /etc/caddy/risarms/*.caddy' /etc/caddy/Caddyfile; then
    cp -a /etc/caddy/Caddyfile "/etc/caddy/Caddyfile.before-risarms-$STAMP"
    echo 'import /etc/caddy/risarms/*.caddy' >> /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile

# Firewall loading and laptop lid-close policy are explicit operator choices.
install -d -m 0755 /usr/local/lib/risarms
install -m 0644 "$SCRIPT_DIR/lib.sh" /usr/local/lib/risarms/common.sh
install -m 0644 "$SCRIPT_DIR/validate-backup.py" /usr/local/lib/risarms/validate-backup.py
for script in backup.sh restore.sh upgrade.sh rollback.sh doctor.sh; do
    install -m 0755 "$SCRIPT_DIR/$script" "/usr/local/sbin/risarms-${script%.sh}"
done

risarms_restart_if_up risarms-rescs
risarms_restart_if_up risarms-core
risarms_restart_if_up caddy
risarms_write_state "$VERSION" "$PREVIOUS_VERSION"

trap - EXIT
printf '%s\n' \
    "Installed CORE $VERSION for Ubuntu Server 24.04 x86_64 (candidate)." \
    "Review /etc/risarms/*.env and /etc/caddy/risarms/portal.caddy." \
    "Enable explicitly: sudo systemctl enable --now risarms-rescs risarms-core caddy" \
    "Logs: sudo journalctl -u risarms-core -f" \
    "Diagnostics: sudo risarms-doctor"
