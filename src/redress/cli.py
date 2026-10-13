"""Command line: validate, export and inspect the registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .registry import Registry


def cmd_validate(args: argparse.Namespace) -> int:
    reg = Registry.load()
    only = {Path(p).resolve() for p in args.paths} if args.paths else None
    problems = reg.validate(only)
    for p in problems:
        print(p)
    checked = len(only) if only else len(reg.files)
    print(f"{'FAIL' if problems else 'OK'}: {checked} file(s) checked, {len(problems)} problem(s)", file=sys.stderr)
    return 1 if problems else 0


def cmd_stats(args: argparse.Namespace) -> int:
    print(json.dumps(Registry.load().stats(), indent=2))
    return 0


def cmd_stale(args: argparse.Namespace) -> int:
    rows = Registry.load().stale(args.days)
    for rel, where, lv in rows:
        print(f"{lv}  {rel}: {where}")
    print(f"{len(rows)} item(s) not verified in the last {args.days} days", file=sys.stderr)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    reg = Registry.load()
    problems = reg.validate()
    if problems:
        print(f"refusing to export: {len(problems)} validation problem(s); run 'redress validate'", file=sys.stderr)
        return 1
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reg.export(), indent=1, ensure_ascii=False))
    print(f"wrote {out}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="redress", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check registry files against the schema and cross references")
    p.add_argument("paths", nargs="*", help="limit the report to these files (default: all)")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("stats", help="count companies, playbooks, regulators and rules")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("stale", help="list items not verified recently")
    p.add_argument("--days", type=int, default=180)
    p.set_defaults(func=cmd_stale)

    p = sub.add_parser("export", help="write the whole registry as one JSON file")
    p.add_argument("-o", "--output", default="dist/registry.json")
    p.set_defaults(func=cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
