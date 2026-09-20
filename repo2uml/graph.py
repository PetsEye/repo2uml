"""File dependency graph (stdlib only)."""
from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from .parsers.base import ModuleInfo


def _norm_import(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    # strip alias: '"pkg" as x' already handled; keep first token
    return raw.split()[0].strip("'\"")


def resolve_relative(importer: str, raw: str, all_files: set[str]) -> str | None:
    """Resolve './x', '../y' to a repo-relative file if it exists."""
    if not raw.startswith("."):
        return None
    base = PurePosixPath(importer).parent
    cand = (base / raw)
    for suffix in ("", ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".java", "/index.ts", "/index.js", "/__init__.py"):
        t = str(cand) + suffix if suffix and not str(cand).endswith(suffix) else str(cand)
        t = t.replace("//", "/")
        if t in all_files:
            return t
        # try without leading ./
        t2 = t[2:] if t.startswith("./") else t
        if t2 in all_files:
            return t2
    return None


def build_graph(modules: list[ModuleInfo]) -> tuple[dict[str, set[str]], dict]:
    """file -> set(files it depends on). External pkgs ignored (not files).

    Returns (graph, stats) where stats counts every import as resolved
    (relative/stem) or dropped with a reason: empty, external,
    stem_collision, unresolvable.
    """
    all_files = {m.path for m in modules}
    # index by stem for bare imports like `from auth import x` / `import auth`
    stem_index: dict[str, list[str]] = defaultdict(list)
    for m in modules:
        stem = PurePosixPath(m.path).stem
        stem_index[stem].append(m.path)
        stem_index[PurePosixPath(m.path).name].append(m.path)

    stats: dict = {
        "imports_total": 0,
        "resolved": 0,
        "resolved_relative": 0,
        "resolved_stem": 0,
        "dropped": {"empty": 0, "external": 0, "stem_collision": 0, "unresolvable": 0},
    }
    graph: dict[str, set[str]] = {m.path: set() for m in modules}
    for m in modules:
        for raw in m.imports:
            imp = _norm_import(raw)
            stats["imports_total"] += 1
            if not imp:
                stats["dropped"]["empty"] += 1
                continue
            target = resolve_relative(m.path, imp, all_files)
            if target is not None and target != m.path:
                graph[m.path].add(target)
                stats["resolved"] += 1
                stats["resolved_relative"] += 1
                continue
            if imp.startswith("."):
                # relative import pointing at nothing we scanned
                stats["dropped"]["unresolvable"] += 1
                continue
            # bare-module match: `auth`, `models`, `simulation`
            key = imp.split("/")[-1].split(".")[-1]
            cands = stem_index.get(key, [])
            if not cands:
                stats["dropped"]["external"] += 1
                continue
            # avoid self + prefer same top dir
            top = m.path.split("/")[0] if "/" in m.path else ""
            best = None
            for c in cands:
                if c == m.path:
                    continue
                if c.split("/")[0] == top:
                    best = c
                    break
            if best is None:
                non_self = [c for c in cands if c != m.path]
                if len(non_self) == 1:
                    best = non_self[0]
            if best:
                graph[m.path].add(best)
                stats["resolved"] += 1
                stats["resolved_stem"] += 1
            else:
                stats["dropped"]["stem_collision"] += 1
    total = stats["imports_total"]
    stats["resolution_rate"] = round(stats["resolved"] / total, 3) if total else 1.0
    return graph, stats


def centrality(graph: dict[str, set[str]]) -> dict[str, int]:
    indeg: dict[str, int] = defaultdict(int)
    for src, dsts in graph.items():
        for d in dsts:
            indeg[d] += 1
    scores = {}
    for node, dsts in graph.items():
        scores[node] = len(dsts) + indeg.get(node, 0) * 2
    return scores
