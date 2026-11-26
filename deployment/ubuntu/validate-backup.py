"""Reject traversal, links, devices and paths outside the Ubuntu deployment."""
import sys
import tarfile
from pathlib import Path, PurePosixPath

TREES = ("etc/risarms", "etc/caddy/risarms", "var/lib/risarms/core",
         "var/lib/risarms/rescs", "var/lib/risarms/frontend", "var/lib/risarms/install-state")
FILES = ("etc/caddy/Caddyfile", "etc/systemd/system/risarms-core.service", "etc/systemd/system/risarms-rescs.service",
         "etc/systemd/logind.conf.d/risarms.conf")

def validate(archive):
    with tarfile.open(archive) as tar:
        for member in tar:
            p = PurePosixPath(member.name)
            name = str(p)
            if p.is_absolute() or ".." in p.parts or not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsafe backup member: {member.name}")
            destination = Path('/') / p
            if any(part.is_symlink() for part in (destination, *destination.parents)):
                raise ValueError(f"Restore destination traverses a symbolic link: {member.name}")
            if not (name in FILES or any(name == t or name.startswith(t + "/") for t in TREES)):
                raise ValueError(f"Unexpected backup member: {member.name}")

if __name__ == "__main__":
    validate(sys.argv[1])
