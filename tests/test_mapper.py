"""Smoke tests: parsers, graph, clustering, PlantUML emission."""
from repo2uml import abstract as ab
from repo2uml import emit_puml as emit
from repo2uml import graph as gmod
from repo2uml import inventory
from repo2uml.parsers import parse_go, parse_java, parse_python, parse_typescript
from repo2uml.parsers.base import ModuleInfo


def test_python_routes_models():
    m = parse_python("src/api.py", "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/users')\ndef list_users(): ...\nclass User(Base): __tablename__='u'\n")
    assert m.routes and m.models


def test_ts_routes():
    m = parse_typescript("src/routes/auth.ts", "import express from 'express';\nconst r = express.Router();\nr.post('/login', () => {});\nexport class AuthService {}")
    assert m.routes and "AuthService" in m.classes


def test_drizzle_table_is_model():
    m = parse_typescript("drizzle/schema.ts", "import { sqliteTable, text } from 'drizzle-orm/sqlite-core';\nexport const users = sqliteTable('users', { id: text('id') });")
    assert m.models


def test_end_to_end_clustering():
    mods = [
        parse_python("api/main.py", "from auth.service import x\n@app.get('/x')\ndef h(): ..."),
        parse_python("auth/service.py", "class AuthService: ..."),
        parse_python("game/engine.py", "class GameService: ..."),
        parse_python("sim/loop.py", "class Simulation: ..."),
        parse_python("store/users.py", "class User(Base): __tablename__='u'"),
    ]
    fg = gmod.build_graph(mods)
    comps = ab.cluster(mods, max_nodes=8)
    names = {c.name for c in comps}
    assert "API" in names and "Database" in names
    edges = ab.component_edges(comps, mods, fg)
    puml = emit.emit_component(comps, edges)
    assert puml.startswith("@startuml") and "-->" in puml


def test_go_java_parse():
    g = parse_go("main.go", 'package main\nimport "net/http"\ntype Game struct{}\nfunc main(){ http.HandleFunc("/x", nil) }')
    assert g.classes and g.routes
    j = parse_java("AuthController.java", "import com.app.AuthService;\n@RestController\npublic class AuthController {}")
    assert "AuthController" in j.classes


def test_nextjs_at_alias_import():
    # "@/..." path alias must not collapse to "" (crashed build_graph with IndexError)
    m = parse_typescript(
        "src/components/button.tsx",
        'import { cn } from "@/lib/utils";\nimport { cva } from "class-variance-authority";\n',
    )
    assert "" not in m.imports
    assert any(i.startswith("@/") for i in m.imports)
    utils = parse_typescript("src/lib/utils.ts", "export function cn() {}")
    fg = gmod.build_graph([m, utils])  # must not raise
    assert fg["src/components/button.tsx"] == {"src/lib/utils.ts"}


def test_empty_import_never_crashes_graph():
    m = ModuleInfo(path="a.ts", language="typescript", imports=["", "   ", "./b"])
    b = ModuleInfo(path="b.ts", language="typescript")
    fg = gmod.build_graph([m, b])  # must not raise
    assert fg["a.ts"] == {"b.ts"}


def test_config_files_ignored(tmp_path):
    (tmp_path / "eslint.config.mjs").write_text("export default [];\n")
    (tmp_path / "next-env.d.ts").write_text('/// <reference types="next" />\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("export const x = 1;\n")
    inv = inventory.scan(tmp_path)
    names = [f.as_posix() for f in inv.files]
    assert names == ["src/app.ts"]


def test_grab_bag_cohesion_split():
    # lib/billing <-> lib/usage are linked; the rest are alone -> stay in Lib
    billing = ModuleInfo(path="src/lib/billing.ts", language="typescript",
                         imports=["./usage"], classes=["Billing"])
    usage = ModuleInfo(path="src/lib/usage.ts", language="typescript",
                       imports=["./billing"], classes=["Usage"])
    stray = ModuleInfo(path="src/lib/stray.ts", language="typescript",
                       classes=["Stray"])
    extra = ModuleInfo(path="src/lib/extra.ts", language="typescript")
    mods = [billing, usage, stray, extra]
    fg = gmod.build_graph(mods)
    comps = ab.cluster(mods, max_nodes=8, file_graph=fg)
    names = {c.name for c in comps}
    assert "Lib" in names  # singletons stay
    assert "Billing" in names or "Usage" in names  # linked chunk splits out
    # small focused dirs are untouched
    solo = ModuleInfo(path="src/auth/a.ts", language="typescript", classes=["A"])
    comps2 = ab.cluster([solo], max_nodes=8, file_graph={solo.path: set()})
    assert len(comps2) == 1


def test_flat_source_root_groups_by_dir(tmp_path):
    # lib/*.js (flat layout) must form one Lib group, not filename nodes
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "application.js").write_text("module.exports = {};\n")
    (tmp_path / "lib" / "request.js").write_text("module.exports = {};\n")
    inv = inventory.scan(tmp_path)
    assert sorted(f.as_posix() for f in inv.files) == ["lib/application.js", "lib/request.js"]
    assert ab._top_dir("lib/application.js") == "lib"
    assert ab._top_dir("src/auth/service.ts") == "auth"


def test_examples_dir_ignored(tmp_path):
    (tmp_path / "examples" / "auth").mkdir(parents=True)
    (tmp_path / "examples" / "auth" / "index.js").write_text("var app = null;\n")
    (tmp_path / "index.js").write_text("module.exports = {};\n")
    inv = inventory.scan(tmp_path)
    assert [f.as_posix() for f in inv.files] == ["index.js"]


def test_entry_points_become_api():    # framework-style repo: no routes anywhere, entry file is the front door
    idx = ModuleInfo(path="index.js", language="javascript", imports=["./lib/express"])
    lib = ModuleInfo(path="lib/express.js", language="javascript", classes=["Express"])
    comps = ab.cluster([idx, lib], max_nodes=8,
                       file_graph={"index.js": {"lib/express.js"}, "lib/express.js": set()},
                       entry_points={"index.js"})
    by_name = {c.name: c for c in comps}
    assert "API" in by_name and by_name["API"].files == ["index.js"]


def test_routes_ignore_comments_and_req_res():
    m = parse_typescript(
        "lib/response.js",
        "// app.get('/fake', () => {})\n"
        "/* router.post('/also-fake', h) */\n"
        "res.get('Content-Type');\n"
        "const url = 'https://example.com/a';\n"
        "r.post('/login', () => {});\n",
    )
    assert m.routes == ["/login"]


def test_nextjs_route_files_are_api_not_keyword_matched():
    # [username] contains "user" but these are route files by framework contract
    for p in ("src/app/[username]/[repo]/page.tsx",
              "src/app/api/chat/route.ts",
              "src/app/layout.tsx"):
        m = ModuleInfo(path=p, language="typescript")
        name, layer = ab._classify(m)
        assert name == "API", (p, name)


def test_http_client_calls_are_not_routes():
    m = parse_typescript(
        "src/components/api-key-dialog.tsx",
        "import axios from 'axios';\nconst api = axios.create({});\n"
        "async function save() { await api.post('/key', { key }); }\n",
    )
    assert not m.routes


def test_server_dir_services_are_not_api():
    m = ModuleInfo(path="src/server/generate/mermaid.ts", language="typescript")
    name, layer = ab._classify(m)
    assert name == "Server", name
    m2 = ModuleInfo(path="src/server/routes.ts", language="typescript")
    assert ab._classify(m2)[0] == "API"


def test_overflow_goes_to_other_not_into_real_nodes():
    mods = [ModuleInfo(path=f"src/mod{i}/a.ts", language="typescript") for i in range(10)]
    fg = {m.path: set() for m in mods}
    comps = ab.cluster(mods, max_nodes=4, file_graph=fg)
    by_name = {c.name: c for c in comps}
    assert "Other" in by_name
    assert len(by_name["Other"].files) == 6
    # kept nodes stay pure single-file groups
    for name, c in by_name.items():
        if name != "Other":
            assert len(c.files) == 1, (name, c.files)
