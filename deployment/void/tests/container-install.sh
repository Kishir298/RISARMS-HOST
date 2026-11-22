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

record INFO os "$(. /etc/os-release && printf '%s %s' "$ID" "$VERSION_ID")"
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
    elogind shadow coreutils findutils tar gzip >/tmp/xbps.log 2>&1 ||
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
mkdir -p /var/service
ln -sf /etc/sv/risarms-rescs /var/service/risarms-rescs
ln -sf /etc/sv/risarms-core /var/service/risarms-core
if command -v runsvdir >/dev/null 2>&1; then
    runsvdir /var/service >/tmp/runsvdir.log 2>&1 &
    sleep 12
    sv status risarms-core risarms-rescs >"$REPORT_DIR/runit-status.txt" 2>&1 || true
    cat "$REPORT_DIR/runit-status.txt" | tee -a "$REPORT"
    for service in risarms-core risarms-rescs; do
        if sv status "$service" 2>/dev/null | grep -q '^run:'; then
            record INFO "runit: $service reported running"
        else
            record INFO "runit: $service did not report running (container evidence only)"
        fi
    done
else
    record INFO "runit: runsvdir unavailable"
fi

if [ "$FAILURES" -ne 0 ]; then
    record FAIL summary "$FAILURES installation check(s) failed"
    exit 1
fi
record PASS summary "installation verified in a Void glibc container"
