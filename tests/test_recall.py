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


def test_proto_service_and_messages():
    from repo2uml.parsers import parse_proto
    m = parse_proto("billing/billing.proto",
                    'syntax = "proto3";\npackage billing.v1;\n'
                    'message ChargeReq { string id = 1; }\n'
                    'service Billing { rpc Charge(ChargeReq) returns (ChargeReq); }\n')
    assert "Billing" in m.classes and "Charge" in m.routes
    assert "ChargeReq" in m.models and m.package == "billing.v1"


def test_prisma_models():
    from repo2uml.parsers import parse_prisma
    m = parse_prisma("prisma/schema.prisma",
                     "model User {\n id String @id\n posts Post[]\n}\nmodel Post {\n id String @id\n}\n")
    assert set(m.models) == {"User", "Post"}
    assert m.has_models


def test_kotlin_basics_and_jvm_clique():
    from repo2uml.parsers import parse_kotlin
    k = parse_kotlin("src/UserService.kt",
                     "package com.app;\nimport com.app.UserRepo;\n"
                     "class UserService(private val repo: UserRepo) {\n"
                     "  suspend fun find(id: String): String { return id; }\n}\n")
    assert k.package == "com.app" and "UserService" in k.classes
    assert "find" in k.functions and k.imports == ["UserRepo"]
    j = parse_java("src/UserRepo.java", "package com.app;\npublic class UserRepo {}\n")
    fg, stats = gmod.build_graph([k, j])
    assert fg["src/UserService.kt"] == {"src/UserRepo.java"}


def test_spring_bean_and_autowired_wire_files():
    cfg = parse_java("src/Cfg.java",
                     "package com.app;\nimport com.app.Store;\n"
                     "@Configuration\npublic class Cfg {\n"
                     "  @Bean\n  public Store store() { return new Store(); }\n}\n")
    assert "Store" in cfg.di_refs
    ctrl = parse_java("src/Ctrl.java",
                      "package com.app;\n"
                      "public class Ctrl {\n"
                      "  @Autowired\n  private Store store;\n"
                      "  public Ctrl(OrderSvc svc) {}\n"
                      "}\n")
    assert "Store" in ctrl.di_refs and "OrderSvc" in ctrl.di_refs
    store = parse_java("src/Store.java", "package com.app;\npublic class Store {}\n")
    svc = parse_java("src/OrderSvc.java", "package com.app;\npublic class OrderSvc {}\n")
    fg, stats = gmod.build_graph([cfg, ctrl, store, svc])
    # same-package clique links everything; DI edges must be among them
    assert {"src/Store.java"} <= fg["src/Cfg.java"]
    assert {"src/Store.java", "src/OrderSvc.java"} <= fg["src/Ctrl.java"]
    assert stats["resolved_symbol"] == 3


def test_spring_requestmapping_prefix_composes():
    m = parse_java("src/C.java",
                   "@RestController\n@RequestMapping(\"/api\")\npublic class C {\n"
                   "  @GetMapping(\"/u\")\n  public String u() { return \"x\"; }\n}\n")
    assert "/api/u" in m.routes


def test_feign_client_recorded():
    m = parse_java("src/Billing.java",
                   '@FeignClient(name = "billing", url = "${u}")\npublic interface Billing {}\n')
    assert m.external_services == ["billing"]


def test_go_fx_wire_and_ent_models():
    w = parse_go("main.go",
                 "package main\nimport \"go.uber.org/fx\"\n"
                 "func main() { fx.New(fx.Provide(NewStore, NewHandler)) }\n")
    assert set(w.di_refs) == {"NewStore", "NewHandler"}
    s = parse_go("store/store.go", "package store\nfunc NewStore() {}\n")
    h = parse_go("handler/h.go", "package handler\nfunc NewHandler() {}\n")
    fg, stats = gmod.build_graph([w, s, h])
    assert fg["main.go"] == {"store/store.go", "handler/h.go"}
    assert stats["resolved_symbol"] == 2
    ent = parse_go("ent/user.go",
                   "package ent\ntype User struct {\n ID string `pg:\"id,pk\"`\n}\n")
    assert "User" in ent.models
    chi = parse_go("r.go", "package r\nfunc m() {\n r.Route(\"/u\", func(r chi.Router) {\n r.Get(\"/{id}\", h) }) }\n")
    assert "/u/{id}" in chi.routes


def test_treesitter_seam_upgrades_symbols_when_installed():
    ts = pytest.importorskip("tree_sitter")
    pytest.importorskip("tree_sitter_java")
    from repo2uml.tree_sitter_backend import available, extract_symbols
    assert available("java")
    # package-private method: invisible to the regex parser, visible to TS
    sym = extract_symbols("java", "package com.app;\npublic class C {\n String hidden() { return \"x\"; }\n}\n")
    assert sym is not None
    assert "C" in sym["classes"] and "hidden" in sym["functions"]
    assert sym["package"] == "com.app"
    # parser unions backend symbols over regex results
    m = parse_java("src/C.java", "package com.app;\npublic class C {\n String hidden() { return \"x\"; }\n}\n")
    assert "hidden" in m.functions


def test_treesitter_absent_is_silent():
    # backend never raises: unknown langs -> None, garbage -> empty result
    from repo2uml import tree_sitter_backend as tsb
    assert tsb.extract_symbols("cobol", "IDENTIFICATION DIVISION.") is None
    assert tsb.available("cobol") is False


def test_nested_samples_segment_is_not_ignored(tmp_path):
    # org.springframework.samples: nested `samples` is package structure
    deep = tmp_path / "src" / "main" / "java" / "org" / "springframework" / "samples"
    deep.mkdir(parents=True)
    (deep / "Owner.java").write_text("public class Owner {}\n")
    (tmp_path / "samples").mkdir()
    (tmp_path / "samples" / "demo.py").write_text("X = 1\n")
    from repo2uml import inventory
    inv = inventory.scan(tmp_path)
    names = sorted(f.as_posix() for f in inv.files)
    assert any(n.endswith("Owner.java") for n in names)
    assert not any(n.startswith("samples/") for n in names)
