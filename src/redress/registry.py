"""Load, validate and index the YAML registry."""

from __future__ import annotations

import datetime as dt
import difflib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "schema" / "redress.schema.json"

PHONE_RE = re.compile(r"^(\+1-\d{3}-\d{3}-\d{4}( ext\. \d+)?|\*?#?\d{3,6})$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)
URL_TYPES = {"web_form", "chat", "portal", "social"}


def registry_dir() -> Path:
    return Path(os.environ.get("REDRESS_REGISTRY", REPO_ROOT / "registry"))


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps dates as strings, so JSON Schema sees what the author wrote."""


_Loader.yaml_implicit_resolvers = {
    key: [(tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:timestamp"]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def load_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)


@dataclass
class Problem:
    file: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.where}: {self.message}" if self.where else f"{self.file}: {self.message}"


@dataclass
class Registry:
    root: Path
    sectors: dict[str, dict] = field(default_factory=dict)
    regulator_names: dict[str, str] = field(default_factory=dict)
    issues: dict[str, dict] = field(default_factory=dict)
    companies: dict[str, dict] = field(default_factory=dict)
    regulators: dict[str, dict] = field(default_factory=dict)
    states: dict[str, dict] = field(default_factory=dict)
    rules: dict[str, dict] = field(default_factory=dict)
    files: dict[str, Path] = field(default_factory=dict)  # "company:<id>" -> path
    problems: list[Problem] = field(default_factory=list)
    _alias_index: dict[str, str] = field(default_factory=dict)

    # ---- loading -------------------------------------------------------

    @classmethod
    def load(cls, root: Path | None = None) -> "Registry":
        reg = cls(root=Path(root) if root else registry_dir())
        reg._load_vocab()
        for kind, sub in (("company", "companies"), ("regulator", "regulators"), ("state", "states"), ("rule", "rules")):
            for path in sorted((reg.root / sub).rglob("*.yaml")):
                reg._load_entry(kind, path)
        reg._build_alias_index()
        return reg

    def _rel(self, path: Path) -> str:
        try:
            return str(path.relative_to(self.root.parent))
        except ValueError:
            return str(path)

    def _load_vocab(self) -> None:
        sectors = load_yaml(self.root / "sectors.yaml")
        self.sectors = {s["id"]: s for s in sectors["sectors"]}
        self.regulator_names = {r["id"]: r["name"] for r in sectors["regulators"]}
        issues = load_yaml(self.root / "issues.yaml")
        self.issues = {i["id"]: i for i in issues["issues"]}

    def _load_entry(self, kind: str, path: Path) -> None:
        try:
            data = load_yaml(path)
        except yaml.YAMLError as e:
            self.problems.append(Problem(self._rel(path), "", f"YAML error: {e}"))
            return
        if not isinstance(data, dict) or "id" not in data:
            self.problems.append(Problem(self._rel(path), "", "file must be a mapping with an 'id'"))
            return
        store = {"company": self.companies, "regulator": self.regulators, "state": self.states, "rule": self.rules}[kind]
        if data["id"] in store:
            first = self._rel(self.files[kind + ":" + data["id"]])
            self.problems.append(Problem(self._rel(path), "id", f"duplicate {kind} id '{data['id']}' (also in {first})"))
            return
        if path.stem != data["id"]:
            self.problems.append(Problem(self._rel(path), "id", f"file name must be '{data['id']}.yaml'"))
        store[data["id"]] = data
        self.files[f"{kind}:{data['id']}"] = path

    def _build_alias_index(self) -> None:
        for cid, c in self.companies.items():
            for name in [cid, c.get("name", ""), *c.get("aliases", [])]:
                key = normalize(name)
                if not key:
                    continue
                other = self._alias_index.get(key)
                if other and other != cid:
                    self.problems.append(Problem(self._rel(self.files[f"company:{cid}"]), "aliases", f"alias '{name}' also used by '{other}'"))
                    continue
                self._alias_index[key] = cid

    # ---- lookup --------------------------------------------------------

    def find_company(self, query: str, limit: int = 5) -> list[dict]:
        """Exact alias match first, then substring and fuzzy matches."""
        key = normalize(query)
        if not key:
            return []
        if key in self._alias_index:
            return [self.companies[self._alias_index[key]]]
        hits: list[str] = []
        for alias, cid in self._alias_index.items():
            if (key in alias or alias in key) and cid not in hits:
                hits.append(cid)
        for alias in difflib.get_close_matches(key, list(self._alias_index), n=limit, cutoff=0.75):
            cid = self._alias_index[alias]
            if cid not in hits:
                hits.append(cid)
        return [self.companies[c] for c in hits[:limit]]

    def sector_of(self, company: dict) -> list[str]:
        return [company["sector"], *company.get("also_sectors", [])]

    # ---- validation ----------------------------------------------------

    def validate(self, only: set[Path] | None = None) -> list[Problem]:
        """Schema and cross-reference checks. `only` limits the report to these files."""
        schema = json.loads(SCHEMA_PATH.read_text())
        problems = list(self.problems)
        today = dt.date.today()
        for key, path in self.files.items():
            if only is not None and path.resolve() not in only:
                continue
            kind, eid = key.split(":", 1)
            data = {"company": self.companies, "regulator": self.regulators, "state": self.states, "rule": self.rules}[kind][eid]
            rel = self._rel(path)
            sub = dict(schema)
            sub["$ref"] = f"#/$defs/{kind}"
            for err in sorted(Draft202012Validator(sub).iter_errors(data), key=lambda e: list(e.path)):
                problems.append(Problem(rel, _path(err.path), err.message))
            problems.extend(self._cross_check(kind, data, rel, today))
        if only is not None:
            problems = [p for p in problems if any(p.file == self._rel(o) for o in only)]
        return problems

    def _cross_check(self, kind: str, data: dict, rel: str, today: dt.date) -> list[Problem]:
        out: list[Problem] = []

        def bad(where: str, msg: str) -> None:
            out.append(Problem(rel, where, msg))

        def check_issue(where: str, iid: str) -> None:
            if iid not in self.issues:
                close = difflib.get_close_matches(iid, list(self.issues), n=1)
                bad(where, f"unknown issue '{iid}'" + (f" (did you mean '{close[0]}'?)" if close else ""))

        def check_sector(where: str, sid: str) -> None:
            if sid not in self.sectors:
                bad(where, f"unknown sector '{sid}'")

        def check_regulator(where: str, rid: str) -> None:
            if rid not in self.regulator_names:
                bad(where, f"unknown regulator '{rid}' (add it to registry/sectors.yaml first)")

        def check_date(where: str, value: Any) -> None:
            if isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                try:
                    if dt.date.fromisoformat(value) > today:
                        bad(where, f"last_verified {value} is in the future")
                except ValueError:
                    bad(where, f"invalid date {value}")

        def check_channels(prefix: str, channels: list) -> set[str]:
            ids: set[str] = set()
            for i, ch in enumerate(channels or []):
                where = f"{prefix}channels[{i}]"
                cid = ch.get("id")
                if cid in ids:
                    bad(where, f"duplicate channel id '{cid}'")
                ids.add(cid)
                value, ctype = str(ch.get("value", "")), ch.get("type")
                if ctype in ("phone", "fax") and not PHONE_RE.match(value):
                    bad(where, f"phone '{value}' must look like +1-800-555-0100 or a short code like 611")
                if ctype == "email" and not EMAIL_RE.match(value):
                    bad(where, f"email '{value}' is not an email address")
                if ctype in URL_TYPES and not value.startswith(("http://", "https://")):
                    bad(where, f"{ctype} value must be a URL")
                for p in ch.get("purposes", []):
                    check_issue(f"{where}.purposes", p)
                check_date(where, ch.get("last_verified"))
            return ids

        def check_facts(where: str, facts: list) -> None:
            for i, f in enumerate(facts or []):
                for iid in f.get("issues", []):
                    check_issue(f"{where}[{i}].issues", iid)
                check_date(f"{where}[{i}]", f.get("last_verified"))

        if kind == "company":
            for s in [data.get("sector"), *data.get("also_sectors", [])]:
                if s:
                    check_sector("sector", s)
            for r in data.get("regulators", []):
                check_regulator("regulators", r)
            channel_ids = check_channels("", data.get("channels", []))
            for i, rung in enumerate(data.get("escalation", [])):
                if rung.get("channel") and rung["channel"] not in channel_ids:
                    bad(f"escalation[{i}]", f"unknown channel '{rung['channel']}'")
                if rung.get("regulator"):
                    check_regulator(f"escalation[{i}]", rung["regulator"])
            seen_issues: set[str] = set()
            for i, pb in enumerate(data.get("playbooks", [])):
                where = f"playbooks[{i}]"
                check_issue(where, pb.get("issue", ""))
                if pb.get("issue") in seen_issues:
                    bad(where, f"two playbooks for issue '{pb['issue']}'")
                seen_issues.add(pb.get("issue"))
                for j, st in enumerate(pb.get("steps", [])):
                    if st.get("channel") and st["channel"] not in channel_ids:
                        bad(f"{where}.steps[{j}]", f"unknown channel '{st['channel']}'")
                    if st.get("regulator"):
                        check_regulator(f"{where}.steps[{j}]", st["regulator"])
                check_facts(f"{where}.facts", pb.get("facts", []))
            check_facts("facts", data.get("facts", []))
            for i, t in enumerate(data.get("tips", [])):
                if t.get("kind") == "community" and not t.get("source"):
                    bad(f"tips[{i}]", "a community tip needs a source")
                for iid in t.get("issues", []):
                    check_issue(f"tips[{i}].issues", iid)
        elif kind == "regulator":
            if data.get("id") not in self.regulator_names:
                bad("id", f"regulator '{data.get('id')}' is not listed in registry/sectors.yaml")
            for s in data.get("covers_sectors", []):
                check_sector("covers_sectors", s)
            for iid in data.get("covers_issues", []):
                check_issue("covers_issues", iid)
            check_channels("", data.get("channels", []))
            check_facts("facts", data.get("facts", []))
        elif kind == "state":
            seen: set[str] = set()
            for i, ag in enumerate(data.get("agencies", [])):
                where = f"agencies[{i}]"
                if ag.get("id") in seen:
                    bad(where, f"duplicate agency id '{ag['id']}'")
                seen.add(ag.get("id"))
                if not str(ag.get("id", "")).startswith(f"{data.get('id')}-"):
                    bad(where, f"agency id must start with '{data.get('id')}-'")
                for s in ag.get("covers_sectors", []):
                    check_sector(f"{where}.covers_sectors", s)
                check_channels(f"{where}.", ag.get("channels", []))
                check_facts(f"{where}.facts", ag.get("facts", []))
            check_facts("facts", data.get("facts", []))
        elif kind == "rule":
            for s in data.get("applies_to", {}).get("sectors", []):
                check_sector("applies_to.sectors", s)
            for iid in data.get("applies_to", {}).get("issues", []):
                check_issue("applies_to.issues", iid)
            check_facts("points", data.get("points", []))
            check_date("", data.get("last_verified"))
        return out

    # ---- freshness -----------------------------------------------------

    def iter_sourced(self):
        """Yield (file, where, item) for every item that has a source and last_verified."""
        for key, path in self.files.items():
            kind, eid = key.split(":", 1)
            data = {"company": self.companies, "regulator": self.regulators, "state": self.states, "rule": self.rules}[kind][eid]
            yield from _walk_sourced(self._rel(path), "", data)

    def stale(self, days: int, today: dt.date | None = None) -> list[tuple[str, str, str]]:
        today = today or dt.date.today()
        out = []
        for rel, where, item in self.iter_sourced():
            lv = item.get("last_verified")
            try:
                age = (today - dt.date.fromisoformat(lv)).days
            except (TypeError, ValueError):
                continue
            if age > days:
                out.append((rel, where, lv))
        return out

    def stats(self) -> dict[str, Any]:
        by_sector: dict[str, int] = {}
        for c in self.companies.values():
            by_sector[c["sector"]] = by_sector.get(c["sector"], 0) + 1
        return {
            "companies": len(self.companies),
            "companies_by_sector": dict(sorted(by_sector.items())),
            "playbooks": sum(len(c.get("playbooks", [])) for c in self.companies.values()),
            "channels": sum(len(c.get("channels", [])) for c in self.companies.values()),
            "regulators": len(self.regulators),
            "states": len(self.states),
            "rules": len(self.rules),
            "issues": len(self.issues),
            "sectors": len(self.sectors),
        }

    def export(self) -> dict[str, Any]:
        """One JSON document for agents without MCP."""
        return {
            "generated": dt.date.today().isoformat(),
            "sectors": list(self.sectors.values()),
            "issues": list(self.issues.values()),
            "regulators": list(self.regulators.values()),
            "states": list(self.states.values()),
            "rules": list(self.rules.values()),
            "companies": list(self.companies.values()),
        }


def _walk_sourced(rel: str, where: str, node: Any):
    if isinstance(node, dict):
        if "source" in node and "last_verified" in node:
            yield rel, where or "(root)", node
        for k, v in node.items():
            yield from _walk_sourced(rel, f"{where}.{k}" if where else k, v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_sourced(rel, f"{where}[{i}]", v)


def _path(parts) -> str:
    out = ""
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else (f".{p}" if out else str(p))
    return out


def normalize(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()
