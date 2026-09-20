"""Inventory: file walk, language + framework detection."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

IGNORE_DIRS = {
    "node_modules", "vendor", "dist", "build", ".git", ".hg", ".svn",
    "__pycache__", ".venv", "venv", ".tox", "target", "out",
    ".next", ".nuxt", "coverage", ".idea", ".vscode",
}
# demos/samples/docs are not architecture — but only when shallow: a NESTED
# `samples` segment is usually package structure (org.springframework.samples)
SHALLOW_IGNORE_DIRS = {
    "examples", "example", "demo", "demos", "sample", "samples",
    "docs", "doc", "website",
}
IGNORE_SUFFIXES = (".min.js", ".bundle.js", ".map")
# tool configs carry no architecture signal (eslint/vite/next/jest/...)
# and .d.ts files are pure declarations with no imports
IGNORE_FILE_RE = re.compile(r"\.config\.[^.]+$|\.d\.ts$", re.IGNORECASE)
TEST_MARKERS = ("test", "tests", "__tests__", "spec", "e2e", "testing")

EXT_LANG = {
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".py": "python", ".go": "go", ".java": "java", ".kt": "kotlin",
    ".kts": "kotlin", ".proto": "proto", ".prisma": "prisma",
}

# manifest file -> (framework, language)
MANIFESTS = {
    "package.json": None,  # inspect contents
    "requirements.txt": ("django/fastapi/flask", "python"),
    "pyproject.toml": ("python-app", "python"),
    "Pipfile": ("python-app", "python"),
    "go.mod": ("go-modules", "go"),
    "pom.xml": ("spring/maven", "java"),
    "build.gradle": ("spring/gradle", "java"),
    "build.gradle.kts": ("spring/gradle", "java"),
    "Cargo.toml": ("rust", "rust"),
    "Gemfile": ("rails", "ruby"),
    "composer.json": ("php", "php"),
}


@dataclass
class Inventory:
    root: Path
    files: list[Path] = field(default_factory=list)  # relative paths
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    skipped_ignored: int = 0  # dirs/suffixes/config patterns
    skipped_unsupported: int = 0  # known files with unscanned extensions
    truncated: bool = False  # hit max_files cap
    packages: dict[str, str] = field(default_factory=dict)  # import-spec -> dir


def _is_ignored(path: Path, parts: tuple[str, ...]) -> bool:
    if any(d in IGNORE_DIRS for d in parts):
        return True
    if any(d in SHALLOW_IGNORE_DIRS for d in parts[:2]):
        return True
    if any(str(path).endswith(s) for s in IGNORE_SUFFIXES):
        return True
    if IGNORE_FILE_RE.search(path.name):
        return True
    return False


def _manifest_dir(root: Path, rel: Path) -> str:
    parent = rel.parent.as_posix()
    return "" if parent == "." else parent


def _record_js_package(root: Path, rel: Path, packages: dict[str, str]) -> None:
    """Map package.json name -> dir so @org/pkg imports resolve in monorepos."""
    try:
        import json as _json
        data = _json.loads((root / rel).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    name = data.get("name") if isinstance(data, dict) else None
    if isinstance(name, str) and name and name not in packages:
        packages[name] = _manifest_dir(root, rel)


GO_MOD_RE = re.compile(r"^\s*module\s+(\S+)", re.M)


def _record_go_module(root: Path, rel: Path, packages: dict[str, str]) -> None:
    """Map go.mod module path -> dir for nested-module monorepos."""
    try:
        text = (root / rel).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    m = GO_MOD_RE.search(text)
    if m and m.group(1) not in packages:
        packages[m.group(1)] = _manifest_dir(root, rel)


def _detect_js_framework(root: Path, frameworks: list[str]) -> None:
    pkg = root / "package.json"
    if not pkg.exists():
        return
    try:
        text = pkg.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return
    for fw in ("express", "nest", "next", "fastify", "koa", "react", "vue", "nuxt"):
        if f'"{fw}"' in text or f"'{fw}'" in text or f"{fw}" in text:
            frameworks.append(fw)


def _detect_python_framework(root: Path, frameworks: list[str]) -> None:
    for name in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.py"):
        f = root / name
        if not f.exists():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for fw in ("fastapi", "django", "flask", "sqlalchemy"):
            if fw in text and fw not in frameworks:
                frameworks.append(fw)


def scan(root: Path, max_files: int = 20000) -> Inventory:
    root = root.resolve()
    inv = Inventory(root=root)
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        if _is_ignored(path, rel.parts):
            inv.skipped_ignored += 1
            continue
        lang = EXT_LANG.get(path.suffix.lower())
        if lang is None:
            if path.name == "package.json":
                _record_js_package(root, rel, inv.packages)
            elif path.name == "go.mod":
                _record_go_module(root, rel, inv.packages)
            else:
                inv.skipped_unsupported += 1
            continue  # manifests are read from disk for framework detection
        inv.files.append(rel)
        inv.languages[lang] = inv.languages.get(lang, 0) + 1
        count += 1
        if count >= max_files:
            inv.truncated = True
            break

    frameworks: list[str] = []
    _detect_js_framework(root, frameworks)
    _detect_python_framework(root, frameworks)
    if (root / "go.mod").exists():
        frameworks.append("go-modules")
        try:
            if "gin-gonic" in (root / "go.mod").read_text(errors="ignore"):
                frameworks.append("gin")
        except OSError:
            pass
    if (root / "pom.xml").exists():
        frameworks.append("spring/maven")
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        frameworks.append("spring/gradle")
    inv.frameworks = sorted(set(frameworks))

    inv.entry_points = detect_entry_points(root, inv.files)
    return inv


def detect_entry_points(root: Path, files: list[Path]) -> list[str]:
    candidates = [
        "src/main.ts", "src/main.js", "src/index.ts", "src/index.js",
        "src/app.ts", "src/app.js", "main.ts", "main.js", "index.js",
        "app.py", "main.py", "src/main.py", "src/app.py", "manage.py",
        "main.go", "cmd/main.go", "src/main.go",
        "src/main/java", "Application.java",
    ]
    found = []
    names = {str(f).replace("\\", "/"): f for f in files}
    for c in candidates:
        if c in names:
            found.append(c)
    # java: any *Application.java
    for f in files:
        if f.suffix == ".java" and f.name.endswith("Application.java"):
            found.append(str(f).replace("\\", "/"))
    return sorted(set(found))[:10]
