#!/bin/sh
# Verify a CORE server release archive by running the shipped Void installer
# inside a Void glibc container.
#
#   container-install.sh <version> [report-directory]
#
# The archive is expected in /release, mounted read-write so the report and
# evidence land beside it. Installation assertions fail the script; runit
# startup evidence is recorded but does not fail it, because a container is
# not the supported hardware target.
set -eu

VERSION=${1:?release version required}
REPORT_DIR=${2:-/release}
REPORT="$REPORT_DIR/container-install-report.txt"
NAME="CORE-Server-${VERSION}-void-x86_64"
ARCHIVE="/release/${NAME}.tar.gz"

: >"$REPORT"
record() {
    # record <PASS|FAIL|INFO> <check> [detail]
    printf '%s\t%s\t%s\n' "$1" "$2" "${3:-}" | tee -a "$REPORT"
}

FAILURES=0
fail() {
    FAILURES=$((FAILURES + 1))
    record FAIL "$1" "${2:-}"
}

check() {
    # check <description> <command...>
    desc=$1
    shift
    if "$@" >/dev/null 2>&1; then
        record PASS "$desc"
    else
        fail "$desc"
    fi
}

record INFO os "$(. /etc/os-release && printf '%s %s' "${ID:-unknown}" "${VERSION_ID:-rolling}")"
record INFO kernel "$(uname -m)"
record INFO version "$VERSION"

if [ ! -f "$ARCHIVE" ]; then
    fail "archive present" "$ARCHIVE"
    exit 1
fi

if (cd /release && sha256sum -c SHA256SUMS); then
    record PASS "release checksums"
else
    fail "release checksums"
fi

xbps-install -Sy bash python3 python3-pip caddy runit-void nftables \
    elogind shadow coreutils findutils tar gzip curl >/tmp/xbps.log 2>&1 ||
    {
        record FAIL "install runtime packages" "see /tmp/xbps.log"
        cat /tmp/xbps.log
        exit 1
    }
record PASS "install runtime packages"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
tar -xzf "$ARCHIVE" -C "$WORK"

if (cd "$WORK/$NAME" && ./deployment/void/install.sh >/tmp/install.log 2>&1); then
    record PASS "run deployment/void/install.sh"
else
    record FAIL "run deployment/void/install.sh" "see /tmp/install.log"
    tail -n 40 /tmp/install.log
    exit 1
fi

check "core venv imports the pinned version" \
    /opt/risarms/core-venv/bin/python -c \
    "from core.version import __version__; raise SystemExit(0 if __version__ == '${VERSION}' else 1)"
check "rescs venv imports" /opt/risarms/rescs-venv/bin/python -c "import rescs"
# Console scripts embed an absolute interpreter path; after the versioned-venv
# rename they must still run through the stable symlink.
check "core-host console script runs" /opt/risarms/core-venv/bin/core-host --help
check "rescs console script runs" /opt/risarms/rescs-venv/bin/rescs --help
check "risarms-doctor installed" test -x /usr/local/sbin/risarms-doctor
check "risarms-backup installed" test -x /usr/local/sbin/risarms-backup
check "risarms-upgrade installed" test -x /usr/local/sbin/risarms-upgrade
check "risarms-rollback installed" test -x /usr/local/sbin/risarms-rollback
check "runit core service definition" test -f /etc/sv/risarms-core/run
check "runit rescs service definition" test -f /etc/sv/risarms-rescs/run
check "caddy portal configuration" test -f /etc/caddy/risarms/portal.caddy
check "nftables include" test -f /etc/nftables.d/risarms.nft
check "install state records the version" \
    sh -c "grep -qx '${VERSION}' /var/lib/risarms/install-state/version"
check "core.env is 0600" sh -c '[ "$(stat -c %a /etc/risarms/core.env)" = "600" ]'
check "rescs.env is 0600" sh -c '[ "$(stat -c %a /etc/risarms/rescs.env)" = "600" ]'
check "portal html installed" test -f /var/lib/risarms/frontend/index.html
check "services are not enabled by the installer" test ! -e /var/service/risarms-core

# Startup evidence. The container is not the supported hardware target, so a
# non-running service is recorded rather than treated as an install failure.
# Use a private service directory: the image's /var/service is a dangling
# symlink and enabling there is a host-policy decision, not an install check.
SVDIR=/run/risarms-validation-sv
if command -v runsvdir >/dev/null 2>&1; then
    install -d -m 0755 "$SVDIR"
    ln -sf /etc/sv/risarms-rescs "$SVDIR/risarms-rescs"
    ln -sf /etc/sv/risarms-core "$SVDIR/risarms-core"
    # Caddy is installed but deliberately left disabled by the installer; enable
    # it here so the shipped portal configuration is exercised over TLS.
    if [ -e /etc/sv/caddy ]; then
        ln -sf /etc/sv/caddy "$SVDIR/caddy"
    fi
    SVDIR="$SVDIR" runsvdir "$SVDIR" >/tmp/runsvdir.log 2>&1 &
    # Later operator scripts (backup/doctor) must control the same service tree.
    export SVDIR
    sleep 12
    SVDIR="$SVDIR" sv status risarms-core risarms-rescs \
        >"$REPORT_DIR/runit-status.txt" 2>&1 || true
    cat "$REPORT_DIR/runit-status.txt" | tee -a "$REPORT"
    for service in risarms-core risarms-rescs; do
        if SVDIR="$SVDIR" sv status "$service" 2>/dev/null | grep -q '^run:'; then
            record INFO "runit: $service reported running"
        else
            record INFO "runit: $service did not report running (container evidence only)"
            name=${service#risarms-}
            log="/var/log/risarms/$name/current"
            if [ -f "$log" ]; then
                record INFO "runit: $service last log lines"
                tail -n 15 "$log" >>"$REPORT" 2>&1 || true
            fi
        fi
    done
    if [ -s /tmp/runsvdir.log ]; then
        record INFO "runsvdir output"
        tail -n 10 /tmp/runsvdir.log >>"$REPORT" 2>&1 || true
    fi
else
    record INFO "runit: runsvdir unavailable"
fi

# ---------------------------------------------------------------------------
# Extended runtime checks.
#
# These drive the shipped operator scripts and the Caddy front end. A container
# is not a booted Void system: no reboot, no hardware, no kernel-module load and
# no external network are involved, so every result below is container
# evidence, never booted-system or hardware evidence.
# ---------------------------------------------------------------------------
record INFO evidence "container only; no reboot, no hardware, no external network"
SVDIR=${SVDIR:-/run/risarms-validation-sv}

eventually() {
    # eventually <timeout-seconds> <command...>
    limit=$1
    shift
    elapsed=0
    while [ "$elapsed" -lt "$limit" ]; do
        if "$@" >/dev/null 2>&1; then return 0; fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

tcp_open() {
    python3 - "$1" "$2" <<'PY'
import socket
import sys

with socket.socket() as sock:
    sock.settimeout(2)
    raise SystemExit(0 if sock.connect_ex((sys.argv[1], int(sys.argv[2]))) == 0 else 1)
PY
}

core_healthy() {
    # Mirrors risarms_wait_http in lib.sh: any response below 500 means the
    # process is serving, which is all a startup check may require.
    python3 - <<'PY'
import urllib.error
import urllib.request

status = 599
try:
    with urllib.request.urlopen("http://127.0.0.1:8780/api/health", timeout=5) as response:
        status = response.status
except urllib.error.HTTPError as exc:
    status = exc.code
except OSError:
    status = 599
raise SystemExit(0 if status < 500 else 1)
PY
}

# --- Caddy TLS -------------------------------------------------------------
if [ -L "$SVDIR/caddy" ]; then
    record INFO caddy "started through the packaged runit service"
elif command -v caddy >/dev/null 2>&1; then
    caddy run --config /etc/caddy/Caddyfile --adapter caddyfile \
        >/tmp/caddy-run.log 2>&1 &
    record INFO caddy "no runit service in the image; started caddy directly"
fi

if eventually 30 tcp_open 127.0.0.1 443; then
    record PASS "caddy listens on 443"
else
    fail "caddy listens on 443" "$(tail -n 3 /tmp/caddy-run.log 2>/dev/null | tr '\n' ' ')"
fi

ORIGIN=$(sed -n 's/^CORE_PUBLIC_ORIGIN=//p' /etc/risarms/core.env 2>/dev/null | head -n 1)
TLS_HOST=${ORIGIN#https://}
TLS_HOST=${TLS_HOST%%:*}
CA_DIRS="/var/lib/caddy /root/.local/share/caddy /var/lib/risarms/caddy"
TLS_CA=""
elapsed=0
while [ -z "$TLS_CA" ] && [ "$elapsed" -lt 20 ]; do
    for dir in $CA_DIRS; do
        TLS_CA=$(find "$dir" -name root.crt -print -quit 2>/dev/null || true)
        [ -n "$TLS_CA" ] && break
    done
    [ -n "$TLS_CA" ] || sleep 1
    elapsed=$((elapsed + 1))
done

if [ -n "$ORIGIN" ] && [ -n "$TLS_HOST" ] && [ -n "$TLS_CA" ]; then
    if curl -fsS --max-time 20 --cacert "$TLS_CA" \
        --resolve "$TLS_HOST:443:127.0.0.1" "$ORIGIN/api/health" \
        >/tmp/tls-health.json 2>/tmp/tls-health.log; then
        record PASS "caddy TLS serves CORE /api/health over the internal CA" \
            "$(head -c 120 /tmp/tls-health.json | tr '\n' ' ')"
    else
        fail "caddy TLS serves CORE /api/health over the internal CA" \
            "$(tail -n 2 /tmp/tls-health.log | tr '\n' ' ')"
    fi
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
        --resolve "$TLS_HOST:80:127.0.0.1" "http://$TLS_HOST/" || true)
    case "$code" in
        301 | 302 | 307 | 308)
            record PASS "plain HTTP is redirected to HTTPS" "HTTP $code"
            ;;
        *)
            fail "plain HTTP is redirected to HTTPS" "HTTP ${code:-none}"
            ;;
    esac
else
    fail "caddy TLS serves CORE /api/health over the internal CA" \
        "origin='${ORIGIN:-none}' ca='${TLS_CA:-none}'"
fi

# --- Firewall --------------------------------------------------------------
if nft -c -f /etc/nftables.d/risarms.nft >/tmp/nft-syntax.log 2>&1; then
    record PASS "nftables ruleset syntax"
else
    fail "nftables ruleset syntax" "$(tail -n 2 /tmp/nft-syntax.log | tr '\n' ' ')"
fi
if nft -f /etc/nftables.d/risarms.nft >/tmp/nft-load.log 2>&1 &&
    nft list table inet risarms >/dev/null 2>&1; then
    record PASS "nftables ruleset loads and table inet risarms exists"
else
    record INFO "nftables ruleset not loaded" \
        "$(tail -n 1 /tmp/nft-load.log 2>/dev/null | tr '\n' ' ')"
fi

# --- Free-space refusal -----------------------------------------------------
INSTALLED_NOW=$(tr -d '[:space:]' < /var/lib/risarms/install-state/version)
if RISARMS_MIN_FREE_GIB=999999 /usr/local/sbin/risarms-upgrade "$WORK/$NAME" \
    >/tmp/freespace.log 2>&1; then
    fail "upgrade refuses insufficient free space" "upgrade proceeded unexpectedly"
else
    if grep -q 'Need at least' /tmp/freespace.log; then
        record PASS "upgrade refuses insufficient free space"
    else
        fail "upgrade refuses insufficient free space" \
            "$(tail -n 2 /tmp/freespace.log | tr '\n' ' ')"
    fi
fi

# --- Backup and restore -----------------------------------------------------
BACKUP_ARCHIVE=""
if /usr/local/sbin/risarms-backup >/tmp/backup.log 2>&1; then
    BACKUP_ARCHIVE=$(find /var/lib/risarms/backups -maxdepth 1 -name 'risarms-*.tar.gz' |
        sort | tail -n 1)
    record PASS "risarms-backup writes an archive" "$(basename "${BACKUP_ARCHIVE:-none}")"
else
    fail "risarms-backup writes an archive" "$(tail -n 3 /tmp/backup.log | tr '\n' ' ')"
fi
if [ -n "$BACKUP_ARCHIVE" ]; then
    asset=/var/lib/risarms/frontend/index.html
    before=$(sha256sum "$asset" | cut -d' ' -f1)
    rm -f "$asset"
    if /usr/local/sbin/risarms-restore --yes "$BACKUP_ARCHIVE" >/tmp/restore.log 2>&1 &&
        [ -f "$asset" ] &&
        [ "$(sha256sum "$asset" | cut -d' ' -f1)" = "$before" ]; then
        record PASS "risarms-restore returns a deleted asset byte-identically"
    else
        fail "risarms-restore returns a deleted asset byte-identically" \
            "$(tail -n 3 /tmp/restore.log | tr '\n' ' ')"
    fi
fi

# --- Upgrade and rollback ---------------------------------------------------
# A synthetic newer version number exercises the real upgrade/rollback state
# machine; the code itself is unchanged, so this proves the mechanics only.
BASE_VERSION=$INSTALLED_NOW
UPGRADE_VERSION=$(printf '%s\n' "$BASE_VERSION" | awk -F. '{printf "%s.%s.%d-validation\n", $1, $2, $3 + 1}')
UPGRADE_ROOT="$WORK/upgrade-$UPGRADE_VERSION"
cp -a "$WORK/$NAME" "$UPGRADE_ROOT"
python3 - "$UPGRADE_ROOT" "$UPGRADE_VERSION" <<'PY'
import json
import pathlib
import re
import sys

root, version = pathlib.Path(sys.argv[1]), sys.argv[2]
manifest = root / "compatibility.json"
data = json.loads(manifest.read_text(encoding="utf-8"))
data["version"] = version
for component in data.get("components", {}).values():
    component["version"] = version
manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
version_py = root / "CORE-HOST" / "core" / "version.py"
version_py.write_text(
    re.sub(r'__version__\s*=\s*"[^"]*"', f'__version__ = "{version}"',
           version_py.read_text(encoding="utf-8"), count=1),
    encoding="utf-8",
)
PY
record INFO upgrade "synthetic version $UPGRADE_VERSION (same code, version bumped)"

if /usr/local/sbin/risarms-upgrade "$UPGRADE_ROOT" >/tmp/upgrade.log 2>&1; then
    upgraded=$(tr -d '[:space:]' < /var/lib/risarms/install-state/version)
    upgraded_target=$(readlink -f /opt/risarms/core-venv)
    if [ "$upgraded" = "$UPGRADE_VERSION" ] &&
        [ "$upgraded_target" = "/opt/risarms/venvs/$UPGRADE_VERSION/core" ] &&
        eventually 30 core_healthy; then
        record PASS "upgrade activates $UPGRADE_VERSION and CORE stays healthy"
    else
        fail "upgrade activates $UPGRADE_VERSION and CORE stays healthy" \
            "state=$upgraded target=$upgraded_target"
    fi
    if /usr/local/sbin/risarms-rollback >/tmp/rollback.log 2>&1; then
        rolled=$(tr -d '[:space:]' < /var/lib/risarms/install-state/version)
        rolled_target=$(readlink -f /opt/risarms/core-venv)
        if [ "$rolled" = "$BASE_VERSION" ] &&
            [ "$rolled_target" = "/opt/risarms/venvs/$BASE_VERSION/core" ] &&
            eventually 30 core_healthy; then
            record PASS "rollback returns to $BASE_VERSION and CORE stays healthy"
        else
            fail "rollback returns to $BASE_VERSION and CORE stays healthy" \
                "state=$rolled target=$rolled_target"
        fi
    else
        fail "rollback returns to $BASE_VERSION and CORE stays healthy" \
            "$(tail -n 3 /tmp/rollback.log | tr '\n' ' ')"
    fi
else
    fail "upgrade activates $UPGRADE_VERSION and CORE stays healthy" \
        "$(tail -n 3 /tmp/upgrade.log | tr '\n' ' ')"
fi

if /usr/local/sbin/risarms-doctor >/tmp/doctor.log 2>&1; then
    record PASS "risarms-doctor after upgrade and rollback"
else
    fail "risarms-doctor after upgrade and rollback" \
        "$(tail -n 5 /tmp/doctor.log | tr '\n' ' ')"
fi

if [ "$FAILURES" -ne 0 ]; then
    record FAIL summary "$FAILURES installation check(s) failed"
    exit 1
fi
record PASS summary "installation verified in a Void glibc container"
