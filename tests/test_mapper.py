"""Smoke tests: parsers, graph, clustering, PlantUML emission."""
from repo2uml import abstract as ab
from repo2uml import emit_puml as emit
from repo2uml import graph as gmod
from repo2uml.parsers import parse_go, parse_java, parse_python, parse_typescript


def test_python_routes_models():
    m = parse_python("src/api.py", "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/users')\ndef list_users(): ...\nclass User(Base): __tablename__='u'\n")
    assert m.routes and m.models


def test_ts_routes():
    m = parse_typescript("src/routes/auth.ts", "import express from 'express';\nconst r = express.Router();\nr.post('/login', () => {});\nexport class AuthService {}")
    assert m.routes and "AuthService" in m.classes


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
