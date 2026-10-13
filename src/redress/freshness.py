"""The weekly freshness report and the work list for the refresh routine."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .credibility import company_credibility, registry_credibility, verification_signal
from .registry import Registry, _walk_sourced


def _weak_items(reg: Registry) -> list[dict[str, Any]]:
    """Values read from a search snippet or an archive copy, worst-graded companies first."""
    out = []
    for c in reg.companies.values():
        grade = company_credibility(reg, c)["grade"]
        path = reg.files.get(f"company:{c['id']}")
        rel = reg._rel(path) if path else c["id"]
        for _, where, item in _walk_sourced(rel, "", c):
            sig = verification_signal(item)
            if sig in ("search_snippet", "archive"):
                out.append({"file": rel, "where": where, "signal": sig, "grade": grade,
                            "source": item.get("source"), "last_verified": item.get("last_verified")})
    order = {"C": 0, "B": 1, "A": 2}
    return sorted(out, key=lambda x: (order[x["grade"]], x["file"]))


def build(reg: Registry, links: list[dict] | None = None, days: int = 180, today: dt.date | None = None) -> dict[str, Any]:
    today = today or dt.date.today()
    dead = [r for r in (links or []) if r.get("status") == "dead"]
    stale = [{"file": f, "where": w, "last_verified": lv} for f, w, lv in reg.stale(days, today)]
    weak = _weak_items(reg)
    grades = {c["id"]: company_credibility(reg, c, today) for c in reg.companies.values()}
    c_grade = sorted(cid for cid, g in grades.items() if g["grade"] == "C")
    return {
        "generated": today.isoformat(),
        "summary": {**reg.stats(), "credibility": registry_credibility(reg, today)},
        "dead_links": dead,
        "stale": stale,
        "weak": weak,
        "grade_c": c_grade,
    }


def markdown(report: dict[str, Any], limit: int = 60) -> str:
    s = report["summary"]
    cred = s["credibility"]
    lines = [
        f"_Generated {report['generated']} by the weekly freshness job. It updates this issue each week._",
        "",
        f"**{s['companies']} companies** · {s['channels']:,} contacts · {s['playbooks']} playbooks · "
        f"{s.get('dossiers', 0)} dossiers · data verified between {cred['oldest_verified']} and {cred['last_verified']}",
        f"Credibility: A {cred['grades']['A']} · B {cred['grades']['B']} · C {cred['grades']['C']}",
        "",
        f"## Dead links ({len(report['dead_links'])})",
    ]
    for r in report["dead_links"][:limit]:
        lines.append(f"- [ ] `{r.get('code') or '-'}` {r['url']} (used by {', '.join(r.get('used_by', [])[:3])})")
    lines += ["", f"## Not verified in 180+ days ({len(report['stale'])})"]
    for r in report["stale"][:limit]:
        lines.append(f"- [ ] {r['last_verified']} `{r['file']}`: {r['where']}")
    lines += ["", f"## Read only from a search snippet or an archive copy ({len(report['weak'])})",
              "Re-check these on the live page, then set `verified_via: page` or `browser`."]
    for r in report["weak"][:limit]:
        lines.append(f"- [ ] grade {r['grade']} `{r['file']}`: {r['where']} ({r['signal']}) {r['source']}")
    lines += ["", f"## Grade C companies ({len(report['grade_c'])})", ", ".join(f"`{c}`" for c in report["grade_c"]) or "None"]
    lines += ["", "How to help: pick an item, check the official page, fix the YAML, and open a PR "
              "(see CONTRIBUTING.md). Maintainers can also label a data issue `data` to let the refresh routine handle it."]
    return "\n".join(lines) + "\n"


def worklist(report: dict[str, Any], n: int = 15) -> list[dict[str, Any]]:
    """What the refresh routine should re-verify first: dead links, then weak values, then the oldest."""
    items: list[dict[str, Any]] = []
    for r in report["dead_links"]:
        items.append({"kind": "dead_link", "url": r["url"], "used_by": r.get("used_by", [])})
    for r in report["weak"]:
        items.append({"kind": "weak_source", **r})
    for r in sorted(report["stale"], key=lambda r: r["last_verified"]):
        items.append({"kind": "stale", **r})
    return items[:n]


def load_links(path: str | Path | None) -> list[dict] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text())
