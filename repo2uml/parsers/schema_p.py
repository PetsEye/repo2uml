"""Schema-file readers: .proto (gRPC services) and .prisma (DB models).

These files often hold an entire service boundary or data model that no
source parser sees. Both compile down to the shared ModuleInfo shape:
proto services -> routes + classes, prisma models -> models.
"""
from __future__ import annotations

import re

from .base import ModuleInfo

PROTO_SERVICE_RE = re.compile(r"service\s+(\w+)")
PROTO_RPC_RE = re.compile(r"rpc\s+(\w+)\s*\(")
PROTO_MESSAGE_RE = re.compile(r"message\s+(\w+)")
PROTO_IMPORT_RE = re.compile(r"""import\s+["']([^"']+)["']""")
PROTO_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
TEST_RE = re.compile(r"(?:^|/)(?:tests?|__tests__)(?:/|$)")

PRISMA_MODEL_RE = re.compile(r"model\s+(\w+)\s*\{")
PRISMA_ENUM_RE = re.compile(r"enum\s+(\w+)\s*\{")


def parse_proto(rel: str, text: str) -> ModuleInfo:
    info = ModuleInfo(path=rel, language="proto", is_test=bool(TEST_RE.search(rel)))
    pm = PROTO_PACKAGE_RE.search(text)
    if pm:
        info.package = pm.group(1)
    for m in PROTO_IMPORT_RE.finditer(text):
        info.imports.append(m.group(1))
    for m in PROTO_MESSAGE_RE.finditer(text):
        info.classes.append(m.group(1))
        info.models.append(m.group(1))
    for m in PROTO_SERVICE_RE.finditer(text):
        info.classes.append(m.group(1))
    for m in PROTO_RPC_RE.finditer(text):
        info.routes.append(m.group(1))
    return info


def parse_prisma(rel: str, text: str) -> ModuleInfo:
    info = ModuleInfo(path=rel, language="prisma")
    for m in PRISMA_MODEL_RE.finditer(text):
        info.classes.append(m.group(1))
        info.models.append(m.group(1))
    for m in PRISMA_ENUM_RE.finditer(text):
        info.classes.append(m.group(1))
    return info
