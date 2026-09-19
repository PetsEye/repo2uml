"""TypeScript/JavaScript parser (regex-based, stdlib only)."""
from __future__ import annotations

import re

from .base import ModuleInfo

IMPORT_RES = [
    re.compile(r"""import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
    re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
]
CLASS_RE = re.compile(r"(?:export\s+)?(?:default\s+)?class\s+(\w+)")
FUNC_RE = re.compile(r"(?:export\s+)?(?:async\s+)?function\s+(\w+)")
ROUTE_RE = re.compile(
    r"(?:app|router|server)\s*\.\s*(?:get|post|put|delete|patch|use|all)\s*\("
    r"|@(?:Get|Post|Put|Delete|Patch|Controller|Route)\s*\("
)
MODEL_RE = re.compile(
    r"@(?:Entity|Schema|Model)\s*\(|extends\s+(?:BaseEntity|Model|Document)"
    r"|(?:defineModel|new\s+(?:Schema|mongoose\.Schema))"
    r"|(?:pgTable|sqliteTable|mysqlTable)\s*\("
)
TEST_RE = re.compile(r"(?:^|/)(?:tests?|__tests__|e2e|spec)(?:/|$)|\.(?:test|spec)\.")


def parse_typescript(rel: str, text: str) -> ModuleInfo:
    lang = "typescript" if rel.endswith((".ts", ".tsx", ".mts", ".cts")) else "javascript"
    info = ModuleInfo(path=rel, language=lang, is_test=bool(TEST_RE.search(rel)))
    for rx in IMPORT_RES:
        for m in rx.finditer(text):
            raw = m.group(1).strip()
            if not raw:
                continue
            # keep relative and @/-aliased imports as-is; external -> top package
            if raw.startswith(".") or raw.startswith("@/"):
                info.imports.append(raw)
            else:
                info.imports.append(raw.split("/")[0].lstrip("@") or raw)
    for m in CLASS_RE.finditer(text):
        info.classes.append(m.group(1))
    for m in FUNC_RE.finditer(text):
        if m.group(1) not in info.classes:
            info.functions.append(m.group(1))
    # NestJS-style methods inside classes
    for m in re.finditer(r"@(?:Get|Post|Put|Delete|Patch|Route)\s*\(\s*['\"`]([^'\"`]*)", text):
        info.routes.append(m.group(1) or "(route)")
    # Express-style: app.get('/x'), router.post(...), r.get(...) — any ident, path-like first arg
    for m in re.finditer(r"""\b\w+\s*\.\s*(?:get|post|put|delete|patch|use|all)\s*\(\s*['"`]([^'"`]*)""", text):
        if m.group(1).startswith(("/", ":", "*")) or m.group(1) == "":
            info.routes.append(m.group(1) or "(route)")
    if MODEL_RE.search(text):
        # capture model class names nearby
        for m in CLASS_RE.finditer(text):
            if m.group(1) not in info.models:
                info.models.append(m.group(1))
        if not info.models:
            info.models.append("(model)")
    return info
