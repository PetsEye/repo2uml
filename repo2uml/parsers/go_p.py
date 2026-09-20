"""Go parser (regex-based)."""
from __future__ import annotations

import re

from .base import ModuleInfo

IMPORT_BLOCK_RE = re.compile(r"import\s*\(\s*(.*?)\)", re.S)
PACKAGE_RE = re.compile(r"^\s*package\s+(\w+)", re.M)
IMPORT_ONE_RE = re.compile(r'import\s+"([^"]+)"')
IMPORT_LINE_RE = re.compile(r'"([^"]+)"')
STRUCT_RE = re.compile(r"type\s+(\w+)\s+struct")
FUNC_RE = re.compile(r"func\s+(?:\(\s*\w+\s+\*?\w+\s*\)\s*)?(\w+)\s*\(")
ROUTE_RE = re.compile(
    r"(?:HandleFunc|Handle|GET|POST|PUT|DELETE|PATCH|Group|Route)\s*\("
    r"|gin\.|echo\.|mux\.|fiber\."
)
MODEL_RE = re.compile(r" hyperbol|gorm\.|db\.AutoMigrate|TableName\s*\(\)")
TEST_RE = re.compile(r"(?:^|/)tests?(?:/|$)|_test\.go$")


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
    if ROUTE_RE.search(text):
        for rm in re.finditer(r"""(?:HandleFunc|GET|POST|PUT|DELETE|PATCH)\s*\(\s*"([^"]*)""", text):
            info.routes.append(rm.group(1) or "(route)")
        if not info.routes:
            info.routes.append("(route)")
    if "gorm.Model" in text or "AutoMigrate" in text or re.search(r"type\s+\w+\s+struct\s*\{[^}]*gorm:", text):
        for stm in STRUCT_RE.finditer(text):
            if stm.group(1) not in info.models:
                info.models.append(stm.group(1))
    return info
