"""Command-line entry point: ``clinical-graph``."""

import argparse
import sys
from collections.abc import Sequence

from clinical_graph import __version__, paths
from clinical_graph.sources import load_manifest, update_lock, verify


def _cmd_list(_: argparse.Namespace) -> int:
    for source in load_manifest().values():
        print(f"{source.key:10} {source.title} ({source.version})")
        print(f"{'':10} download: {source.download}")
        print(f"{'':10} unpack to: {source.root()}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    return 0 if verify(checksums=not args.no_checksums) else 1


def _cmd_lock(_: argparse.Namespace) -> int:
    update_lock()
    print(f"wrote checksums to {paths.SOURCES_LOCK}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="clinical-graph", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    sources = sub.add_parser("sources", help="inspect the source releases")
    ssub = sources.add_subparsers(dest="action", required=True)
    ssub.add_parser("list", help="show sources and where to put them").set_defaults(
        func=_cmd_list
    )
    check = ssub.add_parser("verify", help="check files exist and match the lock")
    check.add_argument("--no-checksums", action="store_true", help="presence only")
    check.set_defaults(func=_cmd_verify)
    ssub.add_parser("lock", help="record checksums in sources.lock.json").set_defaults(
        func=_cmd_lock
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI."""
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
