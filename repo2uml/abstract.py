"""Abstraction: files -> components (API, *Service, *Store, Simulation, Database)."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .parsers.base import ModuleInfo

LAYER_API = 0
LAYER_SERVICE = 1
LAYER_LOGIC = 2
LAYER_STORE = 3

ROLE_KEYWORDS = [
    (re.compile(r"auth|login|session|user", re.I), "AuthService", LAYER_SERVICE),
    (re.compile(r"game|match|play|lobby", re.I), "GameService", LAYER_SERVICE),
    (re.compile(r"simul", re.I), "Simulation", LAYER_LOGIC),
    (re.compile(r"store|repo|dao|model|schema|entity|db|database|persist", re.I), None, LAYER_STORE),
    (re.compile(r"api|route|controller|handler|endpoint|router|server|app", re.I), None, LAYER_API),
]


@dataclass
class Component:
    name: str
    layer: int
    files: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)


def _top_dir(path: str) -> str:
    parts = path.split("/")
    if len(parts) >= 2 and parts[0] in ("src", "lib", "app", "pkg", "internal", "backend", "server"):
        return parts[1]
    return parts[0] if len(parts) > 1 else "root"


def _classify(module: ModuleInfo) -> tuple[str, int]:
    p = module.path
    low = p.lower()
    if module.has_routes or any(k in low for k in ("route", "controller", "handler", "endpoint", "api", "server", "app.")):
        # entry-ish; but auth routes belong to AuthService
        if re.search(r"auth|login|session", low):
            return "AuthService", LAYER_SERVICE
        return "API", LAYER_API
    if module.has_models:
        # persistence wins over generic `user` keyword (UserStore, not AuthService)
        if re.search(r"user|account|auth", low):
            return "UserStore", LAYER_STORE
        top = _top_dir(p)
        if top not in ("root", "src", "models"):
            return f"{top.capitalize()}Store", LAYER_STORE
        return "Database", LAYER_STORE
    for rx, fixed, layer in ROLE_KEYWORDS:
        if rx.search(p) or any(rx.search(c) for c in module.classes):
            if fixed:
                return fixed, layer
            break
    top = _top_dir(p)
    if top in ("root",):
        # single-file repos: derive from filename
        stem = p.rsplit("/", 1)[-1].split(".")[0]
        stem = re.sub(r"[^A-Za-z0-9]+", "", stem.capitalize())
        if not stem:
            stem = "Core"
        if len(stem) > 20:
            stem = "Core"
        return stem, LAYER_LOGIC
    name = re.sub(r"[^A-Za-z0-9]+", "", top.capitalize())
    # service-ify domain dirs
    if _top_dir(p) and not re.search(r"util|common|shared|config|test|script|asset|doc", top, re.I):
        if len(modules_hint_classes(module)) and not name.endswith(("Service", "Store")):
            pass
    return name, LAYER_LOGIC


def modules_hint_classes(module: ModuleInfo) -> list[str]:
    return module.classes


# dirs that conventionally hold unrelated modules: split cohesive
# file clusters out of them instead of one grab-bag node
GRAB_BAG_DIRS = {
    "lib", "libs", "utils", "util", "common", "shared", "helpers",
    "helper", "core", "internal", "pkg", "base",
}
MIN_SPLIT_SIZE = 4  # groups smaller than this are never split
LARGE_GROUP = 10  # non-grab-bag groups above this size may still split
MIN_CHUNK = 2  # a chunk needs this many mutually-linked files to split out


def _connected_chunks(files: list[str], file_graph: dict[str, set[str]]) -> list[list[str]]:
    """Undirected connected components over internal edges, deterministically ordered."""
    fset = set(files)
    adj: dict[str, set[str]] = {f: set() for f in files}
    for f in files:
        for d in file_graph.get(f, ()):  # outgoing
            if d in fset and d != f:
                adj[f].add(d)
                adj[d].add(f)
    seen: set[str] = set()
    chunks: list[list[str]] = []
    for f in sorted(files):
        if f in seen:
            continue
        stack, chunk = [f], []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            chunk.append(cur)
            stack.extend(sorted(adj[cur] - seen))
        chunks.append(sorted(chunk))
    return sorted(chunks, key=lambda c: c[0])


def _chunk_name(chunk: list[str], file_graph: dict[str, set[str]]) -> str:
    """Name a chunk after its most-connected file's stem (deterministic)."""
    cset = set(chunk)
    def internal_degree(f: str) -> int:
        out = len([d for d in file_graph.get(f, ()) if d in cset])
        inn = len([s for s in chunk if f in file_graph.get(s, ())])
        return out + inn
    best = sorted(chunk, key=lambda f: (-internal_degree(f), f))[0]
    stem = best.rsplit("/", 1)[-1].split(".")[0]
    name = re.sub(r"[^A-Za-z0-9]+", "", stem.capitalize())
    return name or "Core"


def _cohesion_split(
    comps: list[Component],
    file_graph: dict[str, set[str]] | None,
    by_path: dict[str, ModuleInfo],
) -> list[Component]:
    if not file_graph:
        return comps
    out: list[Component] = []
    for c in comps:
        if c.name in ("API", "Database") or len(c.files) < MIN_SPLIT_SIZE:
            out.append(c)
            continue
        top = _top_dir(c.files[0]).lower() if c.files else ""
        if top not in GRAB_BAG_DIRS and len(c.files) <= LARGE_GROUP:
            out.append(c)
            continue
        chunks = [ch for ch in _connected_chunks(c.files, file_graph) if len(ch) >= MIN_CHUNK]
        if not chunks:
            out.append(c)
            continue
        taken = {f for ch in chunks for f in ch}
        rest = sorted(set(c.files) - taken)
        if not rest:
            # everything chunked: keep the largest chunk under the original name
            chunks.sort(key=lambda ch: (-len(ch), ch[0]))
            keep, chunks = chunks[0], chunks[1:]
            c.files = sorted(keep)
            c.classes = sorted({cl for f in keep for cl in by_path.get(f, ModuleInfo(f, "")).classes})
            out.append(c)
        else:
            c.files = rest
            c.classes = sorted({cl for f in rest for cl in by_path.get(f, ModuleInfo(f, "")).classes})
            out.append(c)
        for ch in chunks:
            name = _chunk_name(ch, file_graph)
            out.append(Component(
                name=name,
                layer=c.layer,
                files=sorted(ch),
                classes=sorted({cl for f in ch for cl in by_path.get(f, ModuleInfo(f, "")).classes}),
            ))
    return out


def cluster(
    modules: list[ModuleInfo],
    max_nodes: int = 8,
    file_graph: dict[str, set[str]] | None = None,
) -> list[Component]:
    groups: dict[str, Component] = {}
    for m in modules:
        if m.is_test:
            continue
        name, layer = _classify(m)
        c = groups.get(name)
        if c is None:
            c = groups[name] = Component(name=name, layer=layer)
        c.files.append(m.path)
        c.classes.extend(m.classes)
        # strongest layer wins (API beats logic if any file has routes)
        if layer < c.layer and name == "API":
            c.layer = layer
        if layer == LAYER_API and name != "API":
            pass

    comps = list(groups.values())
    by_path = {m.path: m for m in modules}
    comps = _cohesion_split(comps, file_graph, by_path)
    # merge util/config-like small groups into neighbours later; first ensure Database exists
    has_db = any(c.name == "Database" for c in comps)
    stores = [c for c in comps if c.name.endswith("Store")]
    if not has_db and stores:
        # synthesize Database as persistence sink
        comps.append(Component(name="Database", layer=LAYER_STORE))
    elif not has_db and any(m.has_models for m in modules):
        comps.append(Component(name="Database", layer=LAYER_STORE))

    # trim to max_nodes: keep API + Database, drop smallest logic groups (merge into Core)
    comps.sort(key=lambda c: (c.layer, -len(c.files), c.name))
    pinned = [c for c in comps if c.name in ("API", "Database")]
    rest = [c for c in comps if c.name not in ("API", "Database")]
    # prefer components with more files/classes
    rest.sort(key=lambda c: (-len(c.files), c.name))
    budget = max(2, max_nodes)
    keep_rest = rest[: max(0, budget - len(pinned))]
    dropped = rest[len(keep_rest):]
    if dropped:
        core = next((c for c in keep_rest if c.name == "Core"), None)
        if core is None:
            core = Component(name="Core", layer=LAYER_LOGIC)
            # insert by layer order later
            if len(pinned) + len(keep_rest) < budget:
                keep_rest.append(core)
            else:
                # merge into smallest kept
                core = keep_rest[-1] if keep_rest else None
        if core is not None:
            for d in dropped:
                core.files.extend(d.files)
                core.classes.extend(d.classes)
    comps = pinned + keep_rest
    # final ordering: API first, services, logic, stores, Database last
    order = {"API": -1, "Database": 99}
    comps.sort(key=lambda c: (order.get(c.name, c.layer * 10), c.name))
    # rename generic single dirs to Service (e.g. 'Game' -> 'GameService')
    for c in comps:
        if c.name not in ("API", "Database", "Core", "Simulation") and c.layer in (LAYER_SERVICE, LAYER_LOGIC):
            if not c.name.endswith(("Service", "Store", "Core", "Util", "Config")):
                if any(k in c.name.lower() for k in ("game", "auth", "match", "play", "order", "pay", "shop", "user")):
                    c.name = c.name + "Service"
    # dedupe names
    seen: dict[str, int] = {}
    for c in comps:
        if c.name in seen:
            seen[c.name] += 1
            c.name = f"{c.name}{seen[c.name]}"
        else:
            seen[c.name] = 1
    return comps


def component_edges(
    comps: list[Component], modules: list[ModuleInfo], file_graph: dict[str, set[str]]
) -> set[tuple[str, str]]:
    file2comp = {}
    for c in comps:
        for f in c.files:
            file2comp[f] = c.name
    edges: set[tuple[str, str]] = set()
    for src, dsts in file_graph.items():
        sc = file2comp.get(src)
        for d in dsts:
            dc = file2comp.get(d)
            if sc and dc and sc != dc:
                edges.add((sc, dc))
    names = {c.name for c in comps}
    by_name = {c.name: c for c in comps}

    def link(a: str, b: str) -> None:
        if a in names and b in names and a != b:
            edges.add((a, b))

    # semantic backbone so diagrams read top-down even when imports are sparse
    if "API" in names:
        for c in comps:
            if c.name != "API" and c.layer in (1, 2):
                # API depends on services/logic (only add if no contradictory edge flood)
                link("API", c.name)
    # services -> stores/database
    services = [c.name for c in comps if by_name[c.name].layer in (1, 2)]
    stores = [c.name for c in comps if by_name[c.name].layer == 3]
    for s in services:
        for t in stores:
            # only add if service touches persistence-ish files OR graph is sparse
            link(s, t)
    # stores -> Database
    for t in stores:
        if t != "Database":
            link(t, "Database")
    # prune: drop X->Database when X already points at a Store (Store->Database covers it)
    for src in list(names):
        if by_name[src].layer == LAYER_STORE:
            continue
        targets = {b for (a, b) in edges if a == src}
        if "Database" in targets and any(t != "Database" and by_name[t].layer == LAYER_STORE for t in targets):
            edges.discard((src, "Database"))
    # prune: if a node has >4 outgoing, keep edges that follow layer order
    return edges
