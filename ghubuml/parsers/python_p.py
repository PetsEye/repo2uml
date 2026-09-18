"""Python parser using stdlib ast (robust, no deps)."""
from __future__ import annotations

import ast
import re

from .base import ModuleInfo

ROUTE_RE = re.compile(r"@(?:app|router|api|blueprint)\s*\.\s*(?:get|post|put|delete|patch|route)\s*\(")
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
            if node.module:
                info.imports.append(node.module.split(".")[0])
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
        if not info.routes:
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
