"""Check that every URL in the registry still answers.

Many company sites block automated requests, so 401/403/429 count as 'blocked'
(inconclusive), not dead. Only 404/410 and DNS or connection failures count as dead.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass

import httpx

from .registry import Registry

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 redress-linkcheck"
BLOCKED = {401, 403, 405, 406, 429, 451, 999}
DEAD = {404, 410}
# Sites whose bot protection answers 404 even for their home page (checked 2026-10-12).
BOT_404_HOSTS = {"www.ftc.gov", "ftc.gov", "consumer.ftc.gov"}


@dataclass
class Result:
    url: str
    status: str  # ok | blocked | dead | error
    code: int | None
    detail: str
    used_by: list[str]


def collect_urls(reg: Registry) -> dict[str, list[str]]:
    urls: dict[str, list[str]] = defaultdict(list)

    def add(url: str, where: str) -> None:
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            urls[url].append(where)

    def walk(node, where: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                here = f"{where}.{k}"
                if k in ("source", "website", "account_url"):
                    add(v, here)
                elif k == "value" and node.get("type") in ("web_form", "chat", "portal", "social", "app", "in_person"):
                    add(v, here)
                else:
                    walk(v, here)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{where}[{i}]")

    for key, path in reg.files.items():
        kind, eid = key.split(":", 1)
        data = {"company": reg.companies, "regulator": reg.regulators, "state": reg.states, "rule": reg.rules}[kind][eid]
        walk(data, eid)
    from .context import LINK_RE

    for kind, docs in (("dossier", reg.dossiers), ("guide", reg.guides)):
        for key, doc in docs.items():
            for url in LINK_RE.findall(doc.body):
                add(url, f"{kind}:{key}")
    return urls


async def _check(client: httpx.AsyncClient, sem: asyncio.Semaphore, url: str, used_by: list[str]) -> Result:
    async with sem:
        try:
            resp = await client.head(url)
            # Many sites answer HEAD wrongly (404, 403, 405); trust only a GET before calling a link dead.
            if resp.status_code >= 400:
                resp = await client.get(url)
        except httpx.ConnectError as e:
            if "CERTIFICATE_VERIFY_FAILED" in str(e) or "SSL" in str(e):
                return Result(url, "error", None, "TLS certificate not trusted by Python; check in a browser", used_by)
            return Result(url, "dead", None, f"connect error: {e}", used_by)
        except httpx.HTTPError as e:
            return Result(url, "error", None, f"{type(e).__name__}: {e}", used_by)
    code = resp.status_code
    if code < 400:
        return Result(url, "ok", code, str(resp.url) if str(resp.url) != url else "", used_by)
    if code in DEAD and httpx.URL(url).host in BOT_404_HOSTS:
        return Result(url, "blocked", code, "site answers bots with 404; verify by hand", used_by)
    if code in DEAD:
        return Result(url, "dead", code, "", used_by)
    if code in BLOCKED:
        return Result(url, "blocked", code, "site blocks automated checks; verify by hand", used_by)
    return Result(url, "error", code, "", used_by)


async def check_all(reg: Registry, concurrency: int = 16, timeout: float = 20.0, only_prefix: str | None = None) -> list[Result]:
    urls = collect_urls(reg)
    if only_prefix:
        urls = {u: w for u, w in urls.items() if any(x.startswith(only_prefix) for x in w)}
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
        return await asyncio.gather(*(_check(client, sem, u, w) for u, w in sorted(urls.items())))


def report(results: list[Result]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for r in results:
        counts[r.status] += 1
    lines = [f"checked {len(results)} URLs: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))]
    for status in ("dead", "error", "blocked"):
        rows = [r for r in results if r.status == status]
        if not rows:
            continue
        lines.append(f"\n## {status} ({len(rows)})")
        for r in rows:
            lines.append(f"- {r.code or '-'} {r.url}  {r.detail}".rstrip())
            lines.append(f"    used by: {', '.join(r.used_by[:3])}{' …' if len(r.used_by) > 3 else ''}")
    return "\n".join(lines)
