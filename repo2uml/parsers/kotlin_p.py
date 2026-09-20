"""Kotlin parser: Java-adjacent (package/import/class/annotation syntax).

Reuses Java heuristics plus Kotlin `fun` declarations. Precision below the
Java parser for Kotlin-only idioms (data classes caught via `data class`,
companion objects ignored) — documented, improvable via tree-sitter seam.
"""
from __future__ import annotations

import re

from .base import ModuleInfo
from .java_p import (ANNOT_ENTITY, ANNOT_REPO, ANNOT_ROUTE, CLASS_RE,
                     IMPORT_RE, PACKAGE_RE)

FUN_RE = re.compile(r"(?:public|protected|private|internal|open)?\s*(?:suspend\s+)?fun\s+(?:<[^>]*>\s*)?(\w+)\s*[\(<]")
DATA_CLASS_RE = re.compile(r"data\s+class\s+(\w+)")
TEST_RE = re.compile(r"(?:^|/)tests?(?:/|$)|Test\.kt$|Tests\.kt$")


def parse_kotlin(rel: str, text: str) -> ModuleInfo:
    info = ModuleInfo(path=rel, language="kotlin", is_test=bool(TEST_RE.search(rel)))
    pm = PACKAGE_RE.search(text)
    if pm:
        info.package = pm.group(1)
    for m in IMPORT_RE.finditer(text):
        info.imports.append(m.group(1).split(".")[-1])
    for m in CLASS_RE.finditer(text):
        if m.group(1) not in info.classes:
            info.classes.append(m.group(1))
    for m in DATA_CLASS_RE.finditer(text):
        if m.group(1) not in info.classes:
            info.classes.append(m.group(1))
    for m in FUN_RE.finditer(text):
        if m.group(1) not in info.classes:
            info.functions.append(m.group(1))
    if ANNOT_ROUTE.search(text):
        for m in re.finditer(r"""@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)(?:\s*\(\s*(?:value\s*=\s*)?["']([^"']*)""", text):
            info.routes.append(m.group(1) or "(route)")
        if not info.routes:
            info.routes.append("(route)")
    if ANNOT_ENTITY.search(text):
        for c in info.classes:
            if c not in info.models:
                info.models.append(c)
    if ANNOT_REPO.search(text) and not info.models:
        for c in info.classes:
            info.models.append(c + "(repo)")
    return info
