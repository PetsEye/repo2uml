"""Go parser (regex-based)."""
from __future__ import annotations

import re

from .base import ModuleInfo, merge_symbols

IMPORT_BLOCK_RE = re.compile(r"import\s*\(\s*(.*?)\)", re.S)
PACKAGE_RE = re.compile(r"^\s*package\s+(\w+)", re.M)
IMPORT_ONE_RE = re.compile(r'import\s+"([^"]+)"')
IMPORT_LINE_RE = re.compile(r'"([^"]+)"')
STRUCT_RE = re.compile(r"type\s+(\w+)\s+struct")
FUNC_RE = re.compile(r"func\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s*)?(\w+)\s*\(")
ROUTE_RE = re.compile(
    r"(?:HandleFunc|Handle|GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete|Patch|Group|Route)\s*\("
    r"|gin\.|echo\.|mux\.|fiber\.|chi\."
)
MODEL_RE = re.compile(r"gorm\.|db\.AutoMigrate|TableName\s*\(\)")
MODEL_TAG_RE = re.compile(r"type\s+(\w+)\s+struct\s*\{(.*?)\}", re.S)
MODEL_TAG_KEYS = ("gorm:", "ent.", "pg:", "db:", "bson:", "sql:")
DI_RE = re.compile(r"(?:fx|wire)\s*\.\s*(?:Provide|Invoke|Build)\s*\(([^)]*)\)")
DI_PROVIDE_RE = re.compile(r"\.\s*Provide\s*\(([^)]*)\)")
CHI_ROUTE_RE = re.compile(r"""\.Route\s*\(\s*"([^"]+)""")
TEST_RE = re.compile(r"(?:^|/)tests?(?:/|$)|_test\.go$")


def _di_ident(tok: str) -> str | None:
    tok = tok.strip().lstrip("&*[]")
    tok = tok.split(".")[-1]
    if re.fullmatch(r"[A-Z]\w*", tok or ""):
        return tok
    return None


def parse_go(rel: str, text: str) -> ModuleInfo:
    info = ModuleInfo(path=rel, language="go", is_test=bool(TEST_RE.search(rel)))
    pm = PACKAGE_RE.search(text)
    if pm:
        info.package = pm.group(1)
    m = IMPORT_BLOCK_RE.search(text)
    if m:
        for line in m.group(1).splitlines():
            im = IMPORT_LINE_RE.search(line)
            if im:
                raw = im.group(1).strip()
                if not raw:
                    continue
                # keep the full path: the graph strips go.mod module prefixes
                # and falls back to the basename stem when unique
                info.imports.append(raw)
    for im in IMPORT_ONE_RE.finditer(text):
        raw = im.group(1).strip()
        if not raw:
            continue
        info.imports.append(raw)
    for stm in STRUCT_RE.finditer(text):
        info.classes.append(stm.group(1))
    for fm in FUNC_RE.finditer(text):
        if fm.group(1) not in ("if", "for", "switch"):
            info.functions.append(fm.group(1))
    merge_symbols(info, "go", text)
    if ROUTE_RE.search(text):
        prefixes = CHI_ROUTE_RE.findall(text)
        for rm in re.finditer(r"""(?:HandleFunc|GET|POST|PUT|DELETE|PATCH|Get|Post|Put|Delete|Patch)\s*\(\s*"([^"]*)""", text):
            path = rm.group(1) or "(route)"
            # chi nesting: r.Route("/u") { r.Get("/{id}") } -> /u/{id}
            if prefixes and path.startswith("/") and not path.startswith(prefixes[0]):
                path = prefixes[0].rstrip("/") + path
            info.routes.append(path)
        if not info.routes:
            info.routes.append("(route)")
    for m in DI_RE.finditer(text):
        for tok in m.group(1).split(","):
            ident = _di_ident(tok)
            if ident and ident not in info.di_refs:
                info.di_refs.append(ident)
    for m in DI_PROVIDE_RE.finditer(text):
        for tok in m.group(1).split(","):
            ident = _di_ident(tok)
            if ident and ident not in info.di_refs:
                info.di_refs.append(ident)
    if "gorm.Model" in text or "AutoMigrate" in text or re.search(r"type\s+\w+\s+struct\s*\{[^}]*gorm:", text):
        for stm in STRUCT_RE.finditer(text):
            if stm.group(1) not in info.models:
                info.models.append(stm.group(1))
    # tag-based models: ent.Schema embeds, bun/pg, db/bson/sql tags
    for m in MODEL_TAG_RE.finditer(text):
        if any(k in m.group(2) for k in MODEL_TAG_KEYS):
            if m.group(1) not in info.models:
                info.models.append(m.group(1))
    return info
