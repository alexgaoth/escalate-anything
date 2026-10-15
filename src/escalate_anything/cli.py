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
        print(f"refusing to export: {len(problems)} validation problem(s); run 'escalate validate'", file=sys.stderr)
        return 1
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(reg.export(), indent=1, ensure_ascii=False))
    print(f"wrote {out}", file=sys.stderr)
    return 0


def cmd_site(args: argparse.Namespace) -> int:
    from .site import build_site

    reg = Registry.load()
    problems = reg.validate()
    if problems:
        print(f"refusing to build the site: {len(problems)} validation problem(s); run 'escalate validate'", file=sys.stderr)
        return 1
    out = Path(args.output)
    counts = build_site(out, reg, base_url=args.base_url)
    html = sum(v for k, v in counts.items() if k.endswith("_pages"))
    print(f"wrote {out}/ ({counts['companies']} companies, {counts['states']} states, {html} HTML pages)", file=sys.stderr)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import serve

    serve(args.transport, args.host, args.port, args.read_only)
    return 0


def _pick(reg: Registry, query: str) -> dict | None:
    from .advisor import NotFound, resolve_company

    try:
        return resolve_company(reg, query)
    except NotFound as e:
        print(e, file=sys.stderr)
        return None


def cmd_lookup(args: argparse.Namespace) -> int:
    reg = Registry.load()
    hits = reg.find_company(args.query, limit=10) if args.query else sorted(reg.companies.values(), key=lambda c: c["id"])
    if args.sector:
        hits = [c for c in hits if args.sector in reg.sector_of(c)]
    for c in hits:
        issues = ", ".join(pb["issue"] for pb in c.get("playbooks", [])) or "generic playbooks only"
        print(f"{c['id']:<28} {c['name']}  [{c['sector']}]\n{'':<28} playbooks: {issues}")
    if not hits:
        print("No match. Try `escalate lookup` with no query to list every company.", file=sys.stderr)
    return 0 if hits else 1


def cmd_playbook(args: argparse.Namespace) -> int:
    from .advisor import NotFound, get_playbook

    reg = Registry.load()
    c = _pick(reg, args.company)
    if not c:
        return 1
    try:
        pb = get_playbook(reg, c["id"], args.issue, args.state)
    except NotFound as e:
        print(e, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(pb, indent=2))
        return 0
    cred = pb["credibility"]
    out = [f"# {pb['company']['name']}: {pb['issue']['name']}",
           f"Verified {cred['last_verified']} · credibility {cred['grade']} "
           f"({round(cred['primary_share'] * 100)}% official or government sources)", ""]
    if pb.get("summary"):
        out += [pb["summary"], ""]
    if pb["evidence"]:
        out += ["## Collect", *[f"- {e}" for e in pb["evidence"]], ""]
    out.append("## Steps")
    for i, st in enumerate(pb["steps"], 1):
        line = f"{i}. {st['do']}"
        if st.get("channel"):
            line += f"\n   → {st['channel']['label']}: {st['channel']['value']}"
        if st.get("regulator"):
            reg_ch = (st["regulator"].get("channels") or [{}])[0]
            line += f"\n   → {st['regulator']['name']}: {reg_ch.get('value', '')}"
        out.append(line)
    if pb["facts"]:
        out += ["", "## Facts (with sources)"]
        out += [f"- {f['claim']}\n  {f['source']} (verified {f['last_verified']})" for f in pb["facts"]]
    if pb["rules"]["in_force"]:
        out += ["", "## Rules in force"]
        out += [f"- {r['title']} ({r['source']})" for r in pb["rules"]["in_force"]]
    out += ["", "## If that fails, escalate"]
    for step in pb["escalation"]:
        target = step.get("channel", {}).get("value") or (step.get("regulator") or {}).get("name") or ""
        if isinstance(step.get("agencies"), list):
            target = ", ".join(a["name"] for a in step["agencies"])
        out.append(f"- {step['rung'].replace('_', ' ')}{': ' + target if target else ''}")
    if pb["known_blockers"]:
        out += ["", "## Watch out", *[f"- {b}" for b in pb["known_blockers"]]]
    if pb["warnings"]:
        out += ["", *[f"! {w}" for w in pb["warnings"]]]
    print("\n".join(out))
    return 0


def cmd_scam_check(args: argparse.Namespace) -> int:
    from .context import scam_check

    text = args.text if args.text else sys.stdin.read()
    r = scam_check(Registry.load(), text, args.company)
    print(f"Risk: {r['risk'].upper()}")
    for f in r["red_flags"]:
        print(f"  ! {f['why']}")
    print("\n".join(f"- {s}" for s in r["next_steps"]))
    print(r["note"])
    return 0 if r["risk"] == "low" else 2


def cmd_setup(args: argparse.Namespace) -> int:
    from .clients import setup

    return setup(args)


def cmd_install(args: argparse.Namespace) -> int:
    from .clients import main as install_main

    return install_main(args)


def cmd_credibility(args: argparse.Namespace) -> int:
    from .credibility import company_credibility

    reg = Registry.load()
    if args.company:
        c = _pick(reg, args.company)
        if not c:
            return 1
        print(json.dumps(company_credibility(reg, c), indent=2))
        return 0
    rows = []
    for c in sorted(reg.companies.values(), key=lambda c: c["id"]):
        cc = company_credibility(reg, c)
        rows.append((cc["grade"], c["id"], cc["primary_share"], cc["last_verified"], cc["oldest_verified"],
                     cc["verified_from"].get("search_snippet", 0) + cc["verified_from"].get("archive", 0), cc["stale_items"]))
    if args.grade:
        rows = [r for r in rows if r[0] == args.grade]
    print(f"{'grade':<6}{'company':<34}{'official':>9}  {'newest':<11}{'oldest':<11}{'weak':>5}{'stale':>6}")
    for g, cid, share, new, old, weak, stale in rows:
        print(f"{g:<6}{cid:<34}{round(share * 100):>8}%  {new or '-':<11}{old or '-':<11}{weak:>5}{stale:>6}")
    return 0


def cmd_freshness(args: argparse.Namespace) -> int:
    from . import freshness

    rep = freshness.build(Registry.load(), freshness.load_links(args.links), args.days)
    if args.worklist:
        print(json.dumps(freshness.worklist(rep, args.worklist), indent=1))
    else:
        print(freshness.markdown(rep))
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    from . import updater
    from .registry import REPO_ROOT, data_root

    if args.status:
        print(json.dumps(updater.status(), indent=2))
        return 0
    if data_root() == REPO_ROOT:
        print("This is a source checkout; update it with: git pull", file=sys.stderr)
        return 0
    try:
        meta = updater.update()
    except Exception as e:
        print(f"Update failed: {e}", file=sys.stderr)
        return 1
    print(f"Updated: {meta['companies']} companies, data verified up to {meta['last_verified']} ({meta['path']})")
    return 0


def cmd_issues(args: argparse.Namespace) -> int:
    from .advisor import sector_issues

    for i in sector_issues(Registry.load(), args.sector):
        print(f"{i['id']:<24} {i['name']}")
    return 0


def cmd_check_links(args: argparse.Namespace) -> int:
    import asyncio

    from .linkcheck import check_all, report

    results = asyncio.run(check_all(Registry.load(), args.concurrency, only_prefix=args.only))
    text = report(results)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n")
    if args.json:
        from .linkcheck import to_json

        Path(args.json).write_text(json.dumps(to_json(results), indent=1))
    dead = sum(r.status == "dead" for r in results)
    return 1 if dead and args.fail_on_dead else 0


def cmd_cases(args: argparse.Namespace) -> int:
    from .store import Store

    db = Store()
    if args.id:
        print(json.dumps(db.get_case(args.id), indent=2))
    else:
        for c in db.list_cases(None if args.all else "open"):
            fu = f"  follow up {c['follow_up']['on']}" if c["follow_up"] else ""
            print(f"#{c['id']} [{c['status']}] {c['company']} / {c['issue']}: {c['summary']}{fu}")
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    from .store import Store

    for f in Store().feedback():
        print(f"#{f['id']} {f['reported_at']} {f['entity']} {f['location'] or ''}: {f['problem']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="escalate", description=__doc__)
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

    p = sub.add_parser("site", help="build the static website (index.html, JSON files, llms.txt)")
    p.add_argument("-o", "--output", default="site-dist")
    p.add_argument("--base-url", default="https://intro.alexgaoth.com/escalate-anything/", help="public URL of the site, used in llms.txt")
    p.set_defaults(func=cmd_site)

    p = sub.add_parser("serve", help="run the MCP server")
    p.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--read-only", action="store_true", help="registry lookups only; no case log (for shared deployments)")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("lookup", help="find companies by name or alias")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--sector")
    p.set_defaults(func=cmd_lookup)

    p = sub.add_parser("playbook", help="print the playbook for a company and issue")
    p.add_argument("company")
    p.add_argument("issue")
    p.add_argument("--state", help="two-letter state code, to resolve state agencies")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_playbook)

    p = sub.add_parser("scam-check", help="check a message for scam red flags (text argument or stdin)")
    p.add_argument("text", nargs="?")
    p.add_argument("--company")
    p.set_defaults(func=cmd_scam_check)

    p = sub.add_parser("setup", help="connect Escalate Anything to your AI apps: find them, review the changes, apply with backups")
    p.add_argument("clients", nargs="*", help="only these app ids (default: every app found)")
    p.add_argument("--yes", action="store_true", help="apply without asking")
    p.add_argument("--source", choices=["auto", "local", "pypi", "git"], default="auto")
    p.add_argument("--read-only", action="store_true")
    p.set_defaults(func=cmd_setup, remove=False)

    for name, remove in (("install", False), ("uninstall", True)):
        p = sub.add_parser(name, help=f"{'remove the server from' if remove else 'add the MCP server to'} AI apps (Claude Desktop, Cursor, VS Code, ...)")
        p.add_argument("clients", nargs="*", help="client ids; run without arguments to list them")
        p.add_argument("--all", action="store_true", help="every client found on this machine")
        p.add_argument("--list", action="store_true")
        p.add_argument("--dry-run", action="store_true", help="show what would change")
        p.add_argument("--source", choices=["auto", "local", "pypi", "git"], default="auto",
                       help="auto: this checkout when run from source, else the PyPI package")
        p.add_argument("--read-only", action="store_true", help="register the server without the case log")
        p.set_defaults(func=cmd_install, remove=remove)

    p = sub.add_parser("credibility", help="credibility grade, source tiers and verification dates per company")
    p.add_argument("company", nargs="?")
    p.add_argument("--grade", choices=["A", "B", "C"])
    p.set_defaults(func=cmd_credibility)

    p = sub.add_parser("freshness", help="weekly freshness report (Markdown) or the refresh work list (JSON)")
    p.add_argument("--links", help="JSON from `escalate check-links --json`")
    p.add_argument("--days", type=int, default=180)
    p.add_argument("--worklist", type=int, metavar="N", help="print the N items the refresh routine should re-verify")
    p.set_defaults(func=cmd_freshness)

    p = sub.add_parser("update", help="download the latest registry data (installed copies; checkouts use git pull)")
    p.add_argument("--status", action="store_true", help="show when data was last downloaded")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("issues", help="list issue ids")
    p.add_argument("--sector")
    p.set_defaults(func=cmd_issues)

    p = sub.add_parser("check-links", help="check that every registry URL still answers")
    p.add_argument("--concurrency", type=int, default=16)
    p.add_argument("--only", help="only URLs used by entries whose id starts with this")
    p.add_argument("--output", help="also write the report to this file")
    p.add_argument("--fail-on-dead", action="store_true")
    p.add_argument("--json", help="also write the results as JSON to this file")
    p.set_defaults(func=cmd_check_links)

    p = sub.add_parser("cases", help="list cases in the local log")
    p.add_argument("id", nargs="?", type=int)
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_cases)

    p = sub.add_parser("feedback", help="list registry problems reported by agents")
    p.set_defaults(func=cmd_feedback)
    return parser


CLI_COMMANDS = {"setup", "install", "uninstall", "update", "playbook", "lookup", "scam-check",
                "credibility", "issues", "freshness", "validate", "stats", "cases", "feedback", "export", "site"}


def serve_main() -> None:
    """Entry point `escalate-anything`. With no command it runs the MCP server; `escalate-anything setup` (and other
    CLI commands) work too, so `uvx escalate-anything setup` is the one command people need."""
    argv = sys.argv[1:]
    if argv and argv[0] in CLI_COMMANDS:
        sys.exit(main(argv))
    sys.exit(main(["serve", *argv]))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
