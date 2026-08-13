"""CLI entry for MERIDIAN V2 (does not invoke v1)."""

from __future__ import annotations

import argparse

from meridian_v2 import __version__
from meridian_v2.config import get_settings


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="meridian_v2", description="MERIDIAN V2 desk (isolated from v1)")
    parser.add_argument("--version", action="version", version=f"meridian_v2 {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    p_info = sub.add_parser("info", help="Show isolation paths and version")
    p_info.set_defaults(func=cmd_info)

    args = parser.parse_args(argv)
    if not getattr(args, "cmd", None):
        parser.print_help()
        return
    args.func(args)


def cmd_info(_args: argparse.Namespace) -> None:
    s = get_settings()
    print(f"meridian_v2 {__version__}")
    print(f"db_path={s.db_path}")
    print(f"host={s.host} port={s.port}")
    print("charter=advisor-only (no broker execution)")


if __name__ == "__main__":
    main()
