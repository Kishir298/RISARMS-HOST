"""Command line entry point for the RISARMS-HOST umbrella."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, bundle, compat
from .checks import run_checks, workspace_checks
from .layout import WORKSPACE_REPOS

EXIT_OK = 0
EXIT_FAIL = 1


def _print_checks(checks, stream=None) -> bool:
    if stream is None:
        stream = sys.stdout
    ok = True
    for check in checks:
        status = "ok" if check.ok else "FAIL"
        detail = f" ({check.detail})" if check.detail else ""
        print(f"[{status}] {check.name}{detail}", file=stream)
        ok = ok and check.ok
    return ok


def cmd_version(args: argparse.Namespace) -> int:
    manifest = compat.load(Path(args.root))
    version = compat.validate(manifest)
    channel = manifest.get("release_channel")
    project = manifest.get("project")
    print(
        f"risarms-host {__version__} "
        f"({channel} {project}, target void x86_64, core {version})"
    )
    return EXIT_OK


def cmd_components(args: argparse.Namespace) -> int:
    root = Path(args.root)
    checks = workspace_checks(root)
    required = [component.name for component in WORKSPACE_REPOS if component.required]
    if args.format == "json":
        print(
            json.dumps(
                {check.name: {"path": check.detail, "present": check.ok}
                 for check in checks},
                indent=2,
                sort_keys=True,
            )
        )
        missing = [
            check.name for check in checks if not check.ok and check.name in required
        ]
        return EXIT_FAIL if missing else EXIT_OK
    print(f"workspace root: {root}")
    _print_checks(checks)
    missing = [check.name for check in checks if not check.ok and check.name in required]
    if missing:
        print("missing required: " + ", ".join(missing), file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = _print_checks(run_checks(Path(args.root)))
    if args.workspace:
        ok = _print_checks(workspace_checks(Path(args.workspace))) and ok
    return EXIT_OK if ok else EXIT_FAIL


def cmd_bundle(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        result = bundle.assemble(Path(args.root), out, as_tar=args.tar)
    except (bundle.BundleError, compat.CompatibilityError) as exc:
        print(f"bundle failed: {exc}", file=sys.stderr)
        return EXIT_FAIL
    print(result)
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="risarms-host",
        description="RISARMS umbrella: workspace layout, release bundles, operator checks.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="Show umbrella and release version")
    version.add_argument("--root", default=".", help="Directory with compatibility.json")
    version.set_defaults(func=cmd_version)

    components = sub.add_parser("components", help="List workspace component checkouts")
    components.add_argument("--root", default=".", help="Workspace root")
    components.add_argument("--format", choices=("text", "json"), default="text")
    components.set_defaults(func=cmd_components)

    doctor = sub.add_parser("doctor", help="Run operator checks (exit 1 on failure)")
    doctor.add_argument("--root", default=".", help="Umbrella or bundle root")
    doctor.add_argument(
        "--workspace",
        default=None,
        help="Also verify sibling component checkouts under this root",
    )
    doctor.set_defaults(func=cmd_doctor)

    bundler = sub.add_parser("bundle", help="Assemble a release bundle")
    bundler.add_argument("--root", default=".", help="Directory with release sources")
    bundler.add_argument("--out", default="release", help="Output directory")
    bundler.add_argument(
        "--tar", action="store_true", help="Also write tarball and SHA256SUMS"
    )
    bundler.set_defaults(func=cmd_bundle)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except compat.CompatibilityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    raise SystemExit(main())
