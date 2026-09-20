"""PlantUML emission (component + package diagrams)."""
from __future__ import annotations

import re

from .abstract import Component


def sanitize(name: str) -> str:
    s = re.sub(r"\W+", "", name)
    if not s:
        return "Comp"
    if s[0].isdigit():
        s = "C" + s
    return s


def unique_ids(names: list[str]) -> dict[str, str]:
    """Map display names to collision-free PlantUML identifiers."""
    idmap: dict[str, str] = {}
    used: dict[str, int] = {}
    for name in names:
        base = sanitize(name)
        n = used.get(base, 0)
        used[base] = n + 1
        idmap[name] = base if n == 0 else f"{base}{n + 1}"
    return idmap


def emit_component(comps: list[Component], edges: set[tuple[str, str]], title: str = "Architecture") -> str:
    lines = ["@startuml", f"title {title}", "skinparam componentStyle rectangle", ""]
    idmap = unique_ids([c.name for c in comps])
    # declare in layer order with stereotypes for readability
    for c in comps:
        stere = ""
        if c.name == "API":
            stere = " <<entryPoint>>"
        elif c.name == "Database":
            stere = " <<database>>"
        detail = f" ({len(c.files)} files)" if len(c.files) > 1 else ""
        lines.append(f"component [{c.name}{detail}] as {idmap[c.name]}{stere}")
    lines.append("")
    for a, b in sorted(edges):
        lines.append(f"{idmap[a]} --> {idmap[b]}")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def emit_package(comps: list[Component], title: str = "Packages") -> str:
    lines = ["@startuml", f"title {title}", ""]
    for c in comps:
        lines.append(f"package \"{c.name}\" {{")
        for f in sorted(c.files)[:20]:
            lines.append(f"  [{f}]")
        if len(c.files) > 20:
            lines.append(f"  [... +{len(c.files) - 20} more]")
        lines.append("}")
    lines.append("@enduml")
    return "\n".join(lines) + "\n"


def emit_ascii(comps: list[Component], edges: set[tuple[str, str]]) -> str:
    names = [c.name for c in comps]
    api = "API" if "API" in names else (names[0] if names else "")
    db = "Database" if "Database" in names else (names[-1] if names else "")
    mid = [n for n in names if n not in (api, db)]
    lines = [f"  {api}", "   │"]
    if mid:
        if len(mid) <= 2:
            for i, n in enumerate(mid):
                lines += ["   ▼", f"  {n}", "   │"] if i < len(mid) - 1 else ["   ▼", f"  {n}", "   │"]
        else:
            half = (len(mid) + 1) // 2
            left, right = mid[:half], mid[half:]
            lines.append("   ├" + "─" * 8 + "┼" + "─" * 8 + "┤")
            lines.append("   ▼" + " " * 8 + "▼")
            lines.append(f"  {('   '.join(left))}    {('   '.join(right))}")
            lines.append("   │" + " " * 8 + "│")
            lines.append("   └" + "─" * 8 + "┬" + "─" * 8 + "┘")
    lines += ["   ▼", f"  {db}"]
    return "\n".join(lines)
