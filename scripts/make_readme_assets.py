"""Regenerate the README images from real data and real CLI output.

    uv run python scripts/make_readme_assets.py
"""

from __future__ import annotations

import subprocess
import sys
from html import escape
from pathlib import Path

from redress.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def run(*args: str) -> str:
    return subprocess.run([sys.executable, "-m", "redress.cli", *args], capture_output=True, text=True, cwd=ROOT).stdout


def banner(stats: dict, dark: bool) -> str:
    bg, fg, sub, chip_bg, chip_fg, accent = (
        ("#0d1117", "#f0f3f6", "#9aa4b2", "#161b22", "#d0d7de", "#3fb950") if dark else
        ("#ffffff", "#1f2328", "#59636e", "#f6f8fa", "#1f2328", "#1a7f37"))
    chips = [
        f"{stats['companies']} companies",
        f"{stats['states']} states + DC agencies",
        f"{stats['channels']:,} verified contacts",
        f"{stats['playbooks']} playbooks",
        "every fact sourced",
    ]
    x, parts = 64, []
    for c in chips:
        w = 18 + len(c) * 8.4
        parts.append(f'<rect x="{x}" y="214" rx="15" width="{w:.0f}" height="30" fill="{chip_bg}" stroke="{sub}" stroke-opacity="0.35"/>'
                     f'<text x="{x + w / 2:.0f}" y="234" text-anchor="middle" font-family="{SANS}" font-size="14" fill="{chip_fg}">{escape(c)}</text>')
        x += w + 10
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="280" viewBox="0 0 1200 280" role="img" aria-label="redress: get it fixed, don't get scammed">
<rect width="1200" height="280" fill="{bg}"/>
<rect x="64" y="58" width="8" height="64" rx="2" fill="{accent}"/>
<text x="88" y="112" font-family="{SANS}" font-size="64" font-weight="700" letter-spacing="-1.5" fill="{fg}">redress</text>
<text x="66" y="160" font-family="{SANS}" font-size="26" font-weight="600" fill="{fg}">Get it fixed. Don&#8217;t get scammed.</text>
<text x="66" y="190" font-family="{SANS}" font-size="19" fill="{sub}">Verified contacts, playbooks and escalation paths for US companies, for you and your AI agent.</text>
{"".join(parts)}
</svg>
'''


def terminal(command: str, output: str, max_lines: int, width: int = 920) -> str:
    import textwrap

    lines = []
    for raw in output.rstrip("\n").splitlines():
        indent = len(raw) - len(raw.lstrip())
        wrapped = textwrap.wrap(raw, width=100, subsequent_indent=" " * (indent + 2), break_on_hyphens=False) or [""]
        lines.extend(wrapped)
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["…"]
    rows = [("$ " + (command if len(command) <= 98 else command[:97] + "…"), "#7ee787")]
    for line in lines:
        color = "#e6edf3"
        if line.startswith("# ") or line.startswith("## "):
            color = "#79c0ff"
        elif line.strip().startswith("→"):
            color = "#a5d6ff"
        elif line.strip().startswith("!") or "not_on_file" in line or "BELONGS_TO_OTHER" in line or "for united-airlines" in line:
            color = "#ffa657"
        elif line.startswith("Risk: HIGH"):
            color = "#ff7b72"
        rows.append((line, color))
    lh, top = 21, 52
    height = top + lh * len(rows) + 24
    text = "".join(
        f'<text x="24" y="{top + i * lh}" font-family="{MONO}" font-size="14" fill="{c}" xml:space="preserve">{escape(t)}</text>'
        for i, (t, c) in enumerate(rows))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(command)}">
<rect width="{width}" height="{height}" rx="10" fill="#0d1117"/>
<circle cx="22" cy="20" r="6" fill="#ff5f56"/><circle cx="42" cy="20" r="6" fill="#ffbd2e"/><circle cx="62" cy="20" r="6" fill="#27c93f"/>
{text}
</svg>
'''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stats = Registry.load().stats()
    (OUT / "banner-light.svg").write_text(banner(stats, dark=False))
    (OUT / "banner-dark.svg").write_text(banner(stats, dark=True))
    (OUT / "demo-playbook.svg").write_text(terminal(
        "redress playbook united-airlines delayed_baggage --state IL",
        run("playbook", "united-airlines", "delayed_baggage", "--state", "IL"), max_lines=26))
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
