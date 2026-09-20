"""Import alias maps: tsconfig/jsconfig paths + conventional bare prefixes.

Resolves `@/lib/x`, `~/lib/x`, `#imports/x`, `@app/*` style imports to
repo-relative file paths instead of dropping them as externals.
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath

# bare prefixes tried against conventional roots when no tsconfig matches
FALLBACK_ROOTS = ("src/", "app/", "lib/", "")


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_aliases(root: Path) -> list[tuple[str, list[str]]]:
    """Return [(prefix, [target templates])] with `*` as wildcard slot.

    Reads tsconfig.json / jsconfig.json compilerOptions.paths (+ one level
    of `extends`). Prefixes keep their trailing form, e.g. `@/` or `@app/`.
    """
    aliases: list[tuple[str, list[str]]] = []
    for name in ("tsconfig.json", "jsconfig.json"):
        cfg_path = root / name
        data = _read_json(cfg_path)
        if not isinstance(data, dict):
            continue
        # one level of extends (relative to the config file)
        if isinstance(data.get("extends"), str):
            ext = _read_json((cfg_path.parent / data["extends"]).resolve())
            if isinstance(ext, dict):
                data = {**ext, **data}
                data["compilerOptions"] = {
                    **(ext.get("compilerOptions") or {}),
                    **(data.get("compilerOptions") or {}),
                }
        opts = data.get("compilerOptions") or {}
        base = str(opts.get("baseUrl") or ".").rstrip("/") + "/"
        if base == "/":
            base = ""
        paths = opts.get("paths") or {}
        for pat, targets in paths.items():
            prefix = pat[:-1] if pat.endswith("*") else pat
            norm = []
            for t in targets or []:
                t = t[:-1] if t.endswith("*") else t
                norm.append((base + t).replace("//", "/"))
            if prefix and norm:
                aliases.append((prefix, norm))
    # longest prefix first so `@app/` beats `@/`
    aliases.sort(key=lambda kv: -len(kv[0]))
    return aliases


def resolve_alias(
    imp: str,
    all_files: set[str],
    aliases: list[tuple[str, list[str]]],
    try_candidate=None,
) -> str | None:
    """Try alias prefixes, then conventional bare prefixes (@/, ~/, #/)."""
    cands: list[str] = []
    for prefix, targets in aliases:
        if imp.startswith(prefix):
            rest = imp[len(prefix):]
            for t in targets:
                cands.append(t + rest if t.endswith("/") or not rest else t + "/" + rest)
    for prefix in ("@/", "~/", "#"):
        if imp.startswith(prefix) and not any(imp.startswith(p) for p, _ in aliases):
            rest = imp[len(prefix):].lstrip("/")
            for root in FALLBACK_ROOTS:
                cands.append(root + rest)
    # scoped leftovers like @org/pkg (no slash-tail match) are not aliases
    for cand in cands:
        hit = try_candidate(cand) if try_candidate else None
        if hit:
            return hit
    return None


