"""Recall fixtures: desired file-edge assertions per construct.

Tests marked xfail(strict=True) document KNOWN gaps from the robustness
audits — they encode the target behavior. When a fix lands, the marker is
removed; strict XPASS fails the suite until then, so nothing rots silently.
"""
import pytest

from repo2uml import graph as gmod
from repo2uml.parsers import parse_go, parse_java, parse_python, parse_typescript
from repo2uml.parsers.base import ModuleInfo


def _graph(mods):
    fg, stats = gmod.build_graph(mods)
    return fg, stats


def test_stats_shape():
    m = ModuleInfo(path="a.py", language="python", imports=["os", "./b"])
    b = ModuleInfo(path="b.py", language="python")
    fg, stats = _graph([m, b])
    assert stats["imports_total"] == 2
    assert stats["resolved"] == 1
    assert stats["resolution_rate"] == 0.5
    assert fg["a.py"] == {"b.py"}


def test_ts_barrel_reexport_chain():
    idx = parse_typescript("src/index.ts", "export * from './b';\n")
    b = parse_typescript("src/b.ts", "export const x = 1;\n")
    a = parse_typescript("src/a.ts", "import { x } from './index';\n")
    fg, _ = _graph([idx, b, a])
    assert fg["src/index.ts"] == {"src/b.ts"}


def test_ts_tilde_alias():
    a = parse_typescript("src/app.ts", "import { x } from '~/lib/a';\n")
    lib = parse_typescript("src/lib/a.ts", "export const x = 1;\n")
    fg, _ = _graph([a, lib])
    assert fg["src/app.ts"] == {"src/lib/a.ts"}


def test_ts_esm_extension_substitution():
    a = parse_typescript("src/a.ts", "import './foo.js';\n")
    foo = parse_typescript("src/foo.ts", "export const x = 1;\n")
    fg, _ = _graph([a, foo])
    assert fg["src/a.ts"] == {"src/foo.ts"}


def test_python_relative_level_only():
    a = parse_python("pkg/a.py", "from . import auth\n")
    auth = parse_python("pkg/auth.py", "X = 1\n")
    fg, _ = _graph([a, auth])
    assert fg["pkg/a.py"] == {"pkg/auth.py"}


def test_python_init_chain():
    init = parse_python("pkg/__init__.py", "from .b import X\n")
    b = parse_python("pkg/b.py", "X = 1\n")
    main = parse_python("main.py", "from pkg import X\n")
    fg, _ = _graph([init, b, main])
    assert fg["pkg/__init__.py"] == {"pkg/b.py"}
    assert fg["main.py"] == {"pkg/__init__.py"}


def test_java_same_package_no_import():
    a = parse_java("src/com/app/A.java", "package com.app;\npublic class A { B b; }\n")
    b = parse_java("src/com/app/B.java", "package com.app;\npublic class B {}\n")
    fg, _ = _graph([a, b])
    assert fg["src/com/app/A.java"] == {"src/com/app/B.java"}


def test_java_long_import_resolves():
    a = parse_java("src/C.java", "import com.example.app.AuthService;\npublic class C {}\n")
    svc = parse_java("src/AuthService.java", "public class AuthService {}\n")
    fg, _ = _graph([a, svc])
    assert fg["src/C.java"] == {"src/AuthService.java"}


def test_stem_collision_drops_and_counts():
    a = ModuleInfo(path="src/a.py", language="python", imports=["utils"])
    u1 = ModuleInfo(path="src/auth/utils.py", language="python")
    u2 = ModuleInfo(path="src/db/utils.py", language="python")
    fg, stats = _graph([a, u1, u2])
    assert fg["src/a.py"] == set()
    assert stats["dropped"]["stem_collision"] == 1


def test_go_module_basename_still_resolves_when_unique():
    main = parse_go("main.go", 'package main\nimport "example.com/m/pkg/auth"\n')
    auth = parse_go("pkg/auth/auth.go", "package auth\n")
    fg, _ = _graph([main, auth])
    assert fg["main.go"] == {"pkg/auth/auth.go"}


def test_ts_monorepo_cross_package():
    web = parse_typescript(
        "apps/web/a.ts", "import { x } from '@myorg/pkg';\nimport { y } from '@myorg/pkg/sub';\n")
    idx = parse_typescript("packages/pkg/index.ts", "export const x = 1;\n")
    sub = parse_typescript("packages/pkg/sub.ts", "export const y = 1;\n")
    pkgs = {"@myorg/pkg": "packages/pkg"}
    fg, stats = gmod.build_graph([web, idx, sub], packages=pkgs)
    assert fg["apps/web/a.ts"] == {"packages/pkg/index.ts", "packages/pkg/sub.ts"}
    assert stats["resolved_package"] == 2


def test_go_nested_module_dir_link():
    main = parse_go("cmd/svc/main.go", 'package main\nimport "example.com/mono/pkgA"\n')
    foo = parse_go("pkgA/foo.go", "package pkga\n")
    pkgs = {"example.com/mono": ""}
    fg, stats = gmod.build_graph([main, foo], packages=pkgs)
    assert fg["cmd/svc/main.go"] == {"pkgA/foo.go"}
    assert stats["resolved_package"] == 1


def test_go_same_package_clique_per_dir():
    a = parse_go("auth/a.go", "package auth\n")
    b = parse_go("auth/b.go", "package auth\n")
    other = parse_go("store/main.go", "package main\n")
    fg, stats = gmod.build_graph([a, b, other])
    assert fg["auth/a.go"] == {"auth/b.go"}
    assert stats["package_links"] == 2
