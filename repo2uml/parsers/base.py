"""Shared ModuleInfo dataclass."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModuleInfo:
    path: str  # repo-relative posix path
    language: str
    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    is_test: bool = False
    package: str = ""  # Java/Kotlin package or Go package name
    di_refs: list[str] = field(default_factory=list)  # wired symbols (@Bean types, fx.Provide args)
    external_services: list[str] = field(default_factory=list)  # FeignClient names etc.

    @property
    def has_routes(self) -> bool:
        return bool(self.routes)

    @property
    def has_models(self) -> bool:
        return bool(self.models)


def merge_symbols(info: "ModuleInfo", lang: str, text: str) -> None:
    """Union tree-sitter symbols into a parsed module when available.

    No-op when tree_sitter isn't installed — keeps the package dependency-free.
    """
    try:
        from ..tree_sitter_backend import extract_symbols
    except ImportError:
        return
    sym = extract_symbols(lang, text)
    if not sym:
        return
    for c in sym["classes"]:
        if c not in info.classes:
            info.classes.append(c)
    for f in sym["functions"]:
        if f not in info.functions and f not in info.classes:
            info.functions.append(f)
    if sym["package"] and not info.package:
        info.package = sym["package"]
