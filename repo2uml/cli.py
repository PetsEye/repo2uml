"""CLI: repo2uml <source> --out ./diagrams"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from . import __version__
from . import abstract as ab
from . import aliases as alias_mod
from . import emit_puml as emit
from . import graph as gmod
from . import ingest, inventory
from .parsers import parse_go, parse_java, parse_python, parse_typescript


def parse_module(root: Path, rel: Path):
    rel_s = rel.as_posix()
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    suf = rel.suffix.lower()
    if suf == ".py":
        return parse_python(rel_s, text)
    if suf in (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs"):
        return parse_typescript(rel_s, text)
    if suf == ".go":
        return parse_go(rel_s, text)
    if suf == ".java":
        return parse_java(rel_s, text)
    return None


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="repo2uml",
        description="Automatic architecture mapper: GitHub repo -> UML (PlantUML).",
    )
    ap.add_argument("source", help="local dir, https://github.com/org/repo, or org/repo")
    ap.add_argument("--out", default="./diagrams", help="output directory")
    ap.add_argument("--max-nodes", type=int, default=8, help="max components in diagram")
    ap.add_argument("--max-files", type=int, default=20000)
    ap.add_argument("--title", default="Architecture")
    ap.add_argument("--no-render", action="store_true", help="skip svg/png render, .puml only")
    ap.add_argument("--format", choices=["svg", "png"], default="svg")
    ap.add_argument("--stats", action="store_true", help="print dropped-import breakdown")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return ap


MAX_FILE_BYTES = 2 * 1024 * 1024  # skip + count larger files (minified/generated)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out = Path(args.out)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"error: cannot create output dir {out}: {e}", file=sys.stderr)
        return 1

    try:
        repo_root, is_temp = ingest.resolve_source(args.source)
    except Exception as e:
        print(f"error: cannot fetch source '{args.source}': {e}", file=sys.stderr)
        return 2
    try:
        inv = inventory.scan(repo_root, max_files=args.max_files)
        modules = []
        oversized = 0
        for rel in inv.files:
            try:
                if (repo_root / rel).stat().st_size > MAX_FILE_BYTES:
                    oversized += 1
                    continue
            except OSError:
                continue
            m = parse_module(repo_root, rel)
            if m is not None:
                modules.append(m)
        if not modules:
            print("No supported source files found.", file=sys.stderr)
            return 2

        file_graph, gstats = gmod.build_graph(
            modules, aliases=alias_mod.load_aliases(repo_root))
        comps = ab.cluster(modules, max_nodes=args.max_nodes, file_graph=file_graph,
                           entry_points=set(inv.entry_points))
        edges = ab.component_edges(comps, modules, file_graph)

        title = re.sub(r"[\r\n]+", " ", args.title)[:120]
        if inv.frameworks:
            title = f"{title} ({', '.join(inv.frameworks)})"
        component_puml = emit.emit_component(comps, edges, title=title)
        package_puml = emit.emit_package(comps, title=f"{title} packages")

        try:
            (out / "architecture.puml").write_text(component_puml)
            (out / "package.puml").write_text(package_puml)
        except OSError as e:
            print(f"error: cannot write to {out}: {e}", file=sys.stderr)
            return 1
        gstats["files_skipped_oversized"] = oversized
        gstats["files_ignored"] = inv.skipped_ignored
        gstats["files_unsupported"] = inv.skipped_unsupported
        gstats["files_truncated"] = inv.truncated
        ir = {
            "source": args.source,
            "languages": inv.languages,
            "frameworks": inv.frameworks,
            "entry_points": inv.entry_points,
            "components": [
                {"name": c.name, "layer": c.layer, "files": sorted(c.files), "classes": sorted(set(c.classes))}
                for c in comps
            ],
            "edges": sorted([list(e) for e in edges]),
            "stats": gstats,
        }
        (out / "architecture.json").write_text(json.dumps(ir, indent=2))

        print(f"Languages: {inv.languages}")
        print(f"Frameworks: {inv.frameworks or ['(none detected)']}")
        print(f"Files analyzed: {len(modules)}  Components: {len(comps)}")
        cuts = []
        if inv.skipped_ignored:
            cuts.append(f"{inv.skipped_ignored} ignored")
        if inv.skipped_unsupported:
            cuts.append(f"{inv.skipped_unsupported} unsupported")
        if oversized:
            cuts.append(f"{oversized} oversized")
        if inv.truncated:
            cuts.append("truncated at --max-files")
        if cuts:
            print(f"Skipped: {', '.join(cuts)}")
        print(f"Imports resolved: {gstats['resolved']}/{gstats['imports_total']} "
              f"({gstats['resolution_rate']:.0%})")
        if args.stats:
            for reason, n in gstats["dropped"].items():
                print(f"  dropped/{reason}: {n}")
        print()
        print(emit.emit_ascii(comps, edges))
        print()
        print(f"Wrote {out / 'architecture.puml'}")
        print(f"Wrote {out / 'package.puml'}")
        print(f"Wrote {out / 'architecture.json'}")

        if not args.no_render:
            from . import render as rend
            got = rend.render(out / "architecture.puml", fmt=args.format)
            if got:
                print(f"Rendered {got}")
            else:
                print("No render backend (plantuml/docker) — .puml only. "
                      "Install Java+plantuml or run with --no-render.", file=sys.stderr)
        return 0
    finally:
        if is_temp:
            shutil.rmtree(str(repo_root.parent if repo_root.name else repo_root),
                          ignore_errors=True) if False else None
            # repo_root = tmpdir/repo ; clean whole tmpdir
            tmpdir = repo_root.parent
            if "repo2uml-" in str(tmpdir):
                shutil.rmtree(str(tmpdir), ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
