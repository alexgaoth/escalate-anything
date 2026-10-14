"""Regenerate the README images from real data and real CLI output.

    uv run python scripts/make_readme_assets.py

Then render the social card to PNG (link previews and the GitHub social preview):

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --hide-scrollbars \\
      --window-size=1200,630 --screenshot=src/escalate_anything/web/og.png docs/assets/social-card.svg

and the logo the same way (--window-size=400,400, docs/assets/logo.svg -> docs/assets/logo.png).
"""

from __future__ import annotations

import subprocess
import sys
from html import escape
from pathlib import Path

from escalate_anything.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"


def run(*args: str) -> str:
    return subprocess.run([sys.executable, "-m", "escalate_anything.cli", *args], capture_output=True, text=True, cwd=ROOT).stdout


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
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="280" viewBox="0 0 1200 280" role="img" aria-label="Escalate Anything: get the upper hand on any big company when they wrong you">
<rect width="1200" height="280" fill="{bg}"/>
<rect x="64" y="58" width="8" height="64" rx="2" fill="{accent}"/>
<text x="88" y="112" font-family="{SANS}" font-size="64" font-weight="700" letter-spacing="-1.5" fill="{fg}">Escalate Anything</text>
<text x="66" y="160" font-family="{SANS}" font-size="26" font-weight="600" fill="{fg}">Get the upper hand on any big company when they wrong you.</text>
<text x="66" y="190" font-family="{SANS}" font-size="19" fill="{sub}">Big companies count on you giving up. This repo will make your agent hunt them down.</text>
{"".join(parts)}
</svg>
'''


def social_card(stats: dict) -> str:
    """1200x630 card for link previews (og.png) and the GitHub social preview."""
    bg, fg, sub, chip_bg, accent = "#0d1117", "#f0f3f6", "#9aa4b2", "#161b22", "#3fb950"
    chips = [
        f"{stats['companies']} US companies",
        f"{stats['playbooks']} playbooks",
        f"{stats['channels']:,} contacts",
        "every fact sourced",
        "works in 13 AI apps",
    ]
    x, parts = 72, []
    for c in chips:
        w = 28 + len(c) * 10.4
        parts.append(f'<rect x="{x}" y="528" rx="20" width="{w:.0f}" height="40" fill="{chip_bg}" stroke="{sub}" stroke-opacity="0.35"/>'
                     f'<text x="{x + w / 2:.0f}" y="554" text-anchor="middle" font-family="{SANS}" font-size="18" fill="#d0d7de">{escape(c)}</text>')
        x += w + 12
    # Escalation ladder on the right: each rung is a step up when the one below stalls.
    steps = ["Support line", "Supervisor / retention", "Executive office", "Regulator: DOT, FCC, CFPB"]
    rungs = []
    for i, label in enumerate(steps):
        y = 432 - i * 88
        top = i == len(steps) - 1
        rungs.append(f'<rect x="790" y="{y}" width="338" height="56" rx="10" fill="{"#0f2a18" if top else chip_bg}" '
                     f'stroke="{accent if top else sub}" stroke-opacity="{1 if top else 0.35}"/>'
                     f'<text x="812" y="{y + 35}" font-family="{SANS}" font-size="19" font-weight="{600 if top else 400}" '
                     f'fill="{fg if top else "#d0d7de"}">{i + 1}  {escape(label)}</text>')
        if i:
            rungs.append(f'<path d="M959 {y + 82} L959 {y + 62} M951 {y + 70} L959 {y + 62} L967 {y + 70}" '
                         f'stroke="{accent}" stroke-width="2.5" fill="none" stroke-linecap="round"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="Escalate Anything: get the upper hand on any big company when they wrong you">
<rect width="1200" height="630" fill="{bg}"/>
<rect x="72" y="84" width="10" height="84" rx="3" fill="{accent}"/>
<text x="102" y="152" font-family="{SANS}" font-size="84" font-weight="700" letter-spacing="-2" fill="{fg}">Escalate Anything</text>
<text x="74" y="236" font-family="{SANS}" font-size="36" font-weight="600" fill="{fg}">Get the upper hand on any big company</text>
<text x="74" y="282" font-family="{SANS}" font-size="36" font-weight="600" fill="{fg}">when they wrong you.</text>
<text x="74" y="346" font-family="{SANS}" font-size="27" fill="{sub}">Big companies count on you giving up.</text>
<text x="74" y="384" font-family="{SANS}" font-size="27" fill="{accent}">This repo will make your agent hunt them down.</text>
<rect x="72" y="428" width="470" height="60" rx="10" fill="{chip_bg}" stroke="{sub}" stroke-opacity="0.35"/>
<text x="96" y="467" font-family="{MONO}" font-size="24" fill="#7ee787">$</text>
<text x="122" y="467" font-family="{MONO}" font-size="24" fill="#e6edf3">uvx escalate-anything setup</text>
{"".join(parts)}
{"".join(rungs)}
</svg>
'''


def logo() -> str:
    """400x400 square logo: an escalation ladder, top rung highlighted."""
    rungs = "".join(
        f'<rect x="{96 + i * 0}" y="{268 - i * 74}" width="{208}" height="48" rx="10" '
        f'fill="{"#3fb950" if i == 2 else "#30363d"}"/>'
        for i in range(3))
    arrow = ('<path d="M200 70 L200 20 M176 44 L200 20 L224 44" stroke="#3fb950" stroke-width="14" '
             'fill="none" stroke-linecap="round" stroke-linejoin="round"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400" role="img" aria-label="Escalate Anything logo">
<rect width="400" height="400" rx="72" fill="#0d1117"/>
{rungs}
<g transform="translate(0 52)">{arrow}</g>
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
    (OUT / "social-card.svg").write_text(social_card(stats))
    (OUT / "logo.svg").write_text(logo())
    (OUT / "demo-playbook.svg").write_text(terminal(
        "escalate playbook united-airlines delayed_baggage --state IL",
        run("playbook", "united-airlines", "delayed_baggage", "--state", "IL"), max_lines=26))
    print("wrote", ", ".join(p.name for p in sorted(OUT.glob("*.svg"))))


if __name__ == "__main__":
    main()
