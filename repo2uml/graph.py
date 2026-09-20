"""File dependency graph (stdlib only)."""
from __future__ import annotations

import posixpath
from collections import defaultdict
from pathlib import PurePosixPath

from .parsers.base import ModuleInfo


def _norm_import(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        return ""
    # strip alias: '"pkg" as x' already handled; keep first token
    return raw.split()[0].strip("'\"")


EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs", ".cts", ".cjs",
              ".py", ".go", ".java")
INDEX_FILES = ("index.ts", "index.tsx", "index.js", "index.jsx", "index.mjs",
               "__init__.py")
# ESM convention: ./foo.js imports foo.ts
ESM_SWAP = {".js": (".ts", ".tsx"), ".jsx": (".tsx",),
            ".mjs": (".mts", ".ts"), ".cjs": (".cts", ".ts")}


def try_candidate(base: str, all_files: set[str]) -> str | None:
    """Resolve an extensionless or extension-bearing base path to a real file."""
    base = posixpath.normpath(base.replace("//", "/"))
    cands = [base]
    p = PurePosixPath(base)
    suf = p.suffix
    if not suf:
        cands.extend(base + e for e in EXTENSIONS)
        cands.extend(base.rstrip("/") + "/" + i for i in INDEX_FILES)
    elif suf in ESM_SWAP:
        cands.extend(str(p.with_suffix(e)) for e in ESM_SWAP[suf])
    for t in cands:
        t = posixpath.normpath(t)
        if t in all_files:
            return t
        t2 = t[2:] if t.startswith("./") else t
        if t2 in all_files:
            return t2
    return None


def _resolve_package(
    imp: str,
    packages: dict[str, str],
    all_files: set[str],
    dir_index: dict[str, list[str]],
) -> list[str]:
    """Resolve `@org/pkg/sub` / `example.com/mod/pkg` to member files."""
    for spec in sorted(packages, key=len, reverse=True):
        if imp != spec and not imp.startswith(spec + "/"):
            continue
        rest = imp[len(spec):].lstrip("/")
        base = packages[spec]
        cand = (base + "/" + rest).strip("/") if rest else base
        hit = try_candidate(cand, all_files)
        if hit:
            return [hit]
        members = [f for f in dir_index.get(cand, [])]
        if members:
            return sorted(members)
    return []


def resolve_relative(importer: str, raw: str, all_files: set[str]) -> str | None:
    """Resolve './x', '../y' to a repo-relative file if it exists."""
    if not raw.startswith("."):
        return None
    base = PurePosixPath(importer).parent
    return try_candidate(str(base / raw), all_files)


def build_graph(
    modules: list[ModuleInfo],
    aliases: list[tuple[str, list[str]]] | None = None,
    packages: dict[str, str] | None = None,
) -> tuple[dict[str, set[str]], dict]:
    """file -> set(files it depends on). External pkgs ignored (not files).

    Returns (graph, stats) where stats counts every import as resolved
    (relative/stem/alias) or dropped with a reason: empty, external,
    stem_collision, unresolvable.
    """
    from . import aliases as alias_mod

    all_files = {m.path for m in modules}
    # index by stem for bare imports like `from auth import x` / `import auth`;
    # __init__.py additionally indexed under its package dir name so
    # `from pkg import X` resolves to pkg/__init__.py
    stem_index: dict[str, list[str]] = defaultdict(list)
    for m in modules:
        stem = PurePosixPath(m.path).stem
        stem_index[stem].append(m.path)
        stem_index[PurePosixPath(m.path).name].append(m.path)
        if PurePosixPath(m.path).name == "__init__.py":
            parent = str(PurePosixPath(m.path).parent)
            if parent and parent != ".":
                stem_index[parent.rsplit("/", 1)[-1]].append(m.path)

    stats: dict = {
        "imports_total": 0,
        "resolved": 0,
        "resolved_relative": 0,
        "resolved_stem": 0,
        "resolved_alias": 0,
        "resolved_package": 0,
        "package_links": 0,
        "dropped": {"empty": 0, "external": 0, "stem_collision": 0, "unresolvable": 0},
    }
    graph: dict[str, set[str]] = {m.path: set() for m in modules}
    # dir -> member files (for package-dir imports like Go's pkg/auth)
    dir_index: dict[str, list[str]] = defaultdict(list)
    for m in modules:
        dir_index[str(PurePosixPath(m.path).parent)].append(m.path)
    # same-package clique (Java needs no import within a package; Go files
    # in one dir share one package): every pair in a package gets an edge.
    # Java packages are globally unique; Go package names repeat per dir
    # (package main everywhere), so Go cliques are per-directory.
    by_package: dict[str, list[str]] = defaultdict(list)
    for m in modules:
        if not m.package:
            continue
        if m.language == "go":
            key = f"go:{PurePosixPath(m.path).parent}:{m.package}"
        else:
            key = f"{m.language}:{m.package}"
        by_package[key].append(m.path)
    for paths in by_package.values():
        if len(paths) < 2:
            continue
        for a in paths:
            for b in paths:
                if a != b and b not in graph[a]:
                    graph[a].add(b)
                    stats["package_links"] += 1
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
            # monorepo packages (@org/pkg, go module paths): strip the
            # mapped prefix, resolve the remainder under its directory
            pkg_hit = _resolve_package(imp, packages or {}, all_files, dir_index)
            if pkg_hit:
                for t in pkg_hit:
                    if t != m.path:
                        graph[m.path].add(t)
                stats["resolved"] += 1
                stats["resolved_package"] += 1
                continue
            # aliased imports (@/, ~/, #/, tsconfig paths) by path join
            alias_hit = alias_mod.resolve_alias(
                imp, all_files, aliases or [],
                lambda cand: try_candidate(cand, all_files),
            )
            if alias_hit is not None and alias_hit != m.path:
                graph[m.path].add(alias_hit)
                stats["resolved"] += 1
                stats["resolved_alias"] += 1
                continue
            if alias_hit is not None:
                continue
            # bare-module match: `auth`, `models`, `simulation`
            key = imp.split("/")[-1].split(".")[-1]
            cands = stem_index.get(key, [])
            if not cands:
                stats["dropped"]["external"] += 1
                continue
            # avoid self + prefer same top dir; ambiguous (2+ viable targets)
            # drops instead of an arbitrary first-hit (a wrong arrow is
            # worse than a missing one for architecture HONESTY)
            top = m.path.split("/")[0] if "/" in m.path else ""
            non_self = [c for c in cands if c != m.path]
            same_top = [c for c in non_self if c.split("/")[0] == top]
            best = None
            if len(same_top) == 1:
                best = same_top[0]
            elif not same_top and len(non_self) == 1:
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
