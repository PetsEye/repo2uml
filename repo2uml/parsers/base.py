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
    package: str = ""  # Java package / Go package name for same-package linking

    @property
    def has_routes(self) -> bool:
        return bool(self.routes)

    @property
    def has_models(self) -> bool:
        return bool(self.models)
