"""Java parser (regex-based)."""
from __future__ import annotations

import re

from .base import ModuleInfo

IMPORT_RE = re.compile(r"import\s+(?:static\s+)?([\w.]+)\s*;")
PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
CLASS_RE = re.compile(r"(?:public\s+|protected\s+|private\s+)?(?:class|interface|enum|record)\s+(\w+)")
METHOD_RE = re.compile(r"(?:public|protected|private)\s+(?:static\s+)?[\w<>\[\]]+\s+(\w+)\s*\(")
ANNOT_ROUTE = re.compile(r"@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping|Route)\b")
ANNOT_SVC = re.compile(r"@(?:Service|Component|Controller|RestController)\b")
ANNOT_REPO = re.compile(r"@(?:Repository|Dao)\b")
ANNOT_ENTITY = re.compile(r"@(?:Entity|Table|Document)\b")
TEST_RE = re.compile(r"(?:^|/)tests?(?:/|$)|Test\.java$|Tests\.java$")


def parse_java(rel: str, text: str) -> ModuleInfo:
    info = ModuleInfo(path=rel, language="java", is_test=bool(TEST_RE.search(rel)))
    pm = PACKAGE_RE.search(text)
    if pm:
        info.package = pm.group(1)
    for m in IMPORT_RE.finditer(text):
        # the dependency is always the last component (the class):
        # import com.example.app.AuthService -> AuthService
        info.imports.append(m.group(1).split(".")[-1])
    for m in CLASS_RE.finditer(text):
        info.classes.append(m.group(1))
    for m in METHOD_RE.finditer(text):
        info.functions.append(m.group(1))
    if ANNOT_ROUTE.search(text):
        for m in re.finditer(r"""@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)(?:\s*\(\s*(?:value\s*=\s*)?["']([^"']*)""", text):
            info.routes.append(m.group(1) or "(route)")
        if not info.routes:
            info.routes.append("(route)")
    if ANNOT_ENTITY.search(text):
        for m in CLASS_RE.finditer(text):
            if m.group(1) not in info.models:
                info.models.append(m.group(1))
    if ANNOT_REPO.search(text) and not info.models:
        for m in CLASS_RE.finditer(text):
            info.models.append(m.group(1) + "(repo)")
    return info
