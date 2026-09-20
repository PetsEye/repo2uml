"""Python parser using stdlib ast (robust, no deps)."""
from __future__ import annotations

import ast
import re

from .base import ModuleInfo

ROUTE_RE = re.compile(r"@(?:app|router|api|blueprint)\s*\.\s*(?:get|post|put|delete|patch|route)\s*\(")
DJANGO_PATH_RE = re.compile(r"""(?<!\.)\bpath\s*\(\s*['"]([^'"]*)""")
FLASK_BLUEPRINT_RE = re.compile(r"""register_blueprint\s*\(\s*\w+\s*(?:,\s*url_prefix\s*=\s*['"]([^'"]+)["'])?""")
FASTAPI_ADD_ROUTE_RE = re.compile(r"""add_api_route\s*\(\s*['"]([^'"]+)""")
FASTAPI_ROUTER_RE = re.compile(r"""(\w+)\s*=\s*APIRouter\s*\(([^)]*)\)""")
FASTAPI_ROUTER_PREFIX_RE = re.compile(r"""prefix\s*=\s*['"]([^'"]+)""")
FASTAPI_DEC_RE = re.compile(r"""@(\w+)\s*\.\s*(?:get|post|put|delete|patch|route)\s*\(\s*['"]([^'"]+)""")
MODEL_RES = [
    re.compile(r"class\s+\w+\s*\((.*?(?:Base|Model|db\.Model|Document).*?)\)"),
    re.compile(r"@(?:dataclass|entity)"),
]
TEST_RE = re.compile(r"(?:^|/)(?:tests?|__tests__|testing)(?:/|$)|(?:test_|_test|spec)")


def parse_python(rel: str, text: str) -> ModuleInfo:
    info = ModuleInfo(path=rel, language="python", is_test=bool(TEST_RE.search(rel)))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return info
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                info.imports.append(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # absolute: keep the SUBMODULE (last component) — `from pkg.b import X`
            # depends on b, not pkg; bare top-level also kept as fallback below
            if node.module and node.level == 0:
                info.imports.append(node.module.split(".")[-1])
                if "." in node.module:
                    info.imports.append(node.module.split(".")[0])
            elif node.level > 0:
                # relative: emit ./-style path the graph resolves against the
                # importer's directory: `from .auth import x` -> ./auth,
                # `from ..models import Y` -> ../models, `from . import auth`
                # -> ./auth per imported name
                prefix = "./" if node.level == 1 else "../" * (node.level - 1)
                if node.module:
                    info.imports.append(prefix + node.module.replace(".", "/"))
                for a in node.names:
                    if a.name != "*":
                        info.imports.append(prefix + a.name)
        elif isinstance(node, ast.ClassDef):
            info.classes.append(node.name)
            bases = [ast.unparse(b) if hasattr(ast, "unparse") else "" for b in node.bases]
            joined = ",".join(bases)
            if any(k in joined for k in ("Base", "Model", "db.Model", "Document", "Table")):
                info.models.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.functions.append(node.name)
    if ROUTE_RE.search(text):
        # capture route paths crudely
        for m in re.finditer(r"""@(?:app|router|api|blueprint)\s*\.\s*(?:get|post|put|delete|patch|route)\s*\(\s*['"]([^'"]+)""", text):
            info.routes.append(m.group(1))
    # FastAPI APIRouter(prefix=...): join prefix onto per-router routes
    router_prefixes: dict[str, str] = {}
    for m in FASTAPI_ROUTER_RE.finditer(text):
        pm = FASTAPI_ROUTER_PREFIX_RE.search(m.group(2) or "")
        if pm:
            router_prefixes[m.group(1)] = pm.group(1)
    for m in FASTAPI_DEC_RE.finditer(text):
        var, path = m.group(1), m.group(2)
        route = router_prefixes.get(var, "") + path
        if route not in info.routes:
            info.routes.append(route)
    # Django urls.py: path("api/", ...) / include() chains mark the URL tree
    for m in DJANGO_PATH_RE.finditer(text):
        if m.group(1) not in info.routes:
            info.routes.append(m.group(1) or "(route)")
    # Flask blueprints: register_blueprint(bp, url_prefix="/auth")
    for m in FLASK_BLUEPRINT_RE.finditer(text):
        info.routes.append(m.group(1) or "(blueprint)")
    # FastAPI add_api_route("/health", ...)
    for m in FASTAPI_ADD_ROUTE_RE.finditer(text):
        if m.group(1) not in info.routes:
            info.routes.append(m.group(1))
    if (ROUTE_RE.search(text) or router_prefixes) and not info.routes:
        info.routes.append("(route)")
    for rx in MODEL_RES:
        if rx.search(text) and not info.models:
            info.models.append("(model)")
            break
    # sqlalchemy table definitions
    if "__tablename__" in text:
        for m in re.finditer(r"class\s+(\w+)", text):
            if m.group(1) not in info.models:
                info.models.append(m.group(1))
    return info
