"""Inventory: file walk, language + framework detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

IGNORE_DIRS = {
    "node_modules", "vendor", "dist", "build", ".git", ".hg", ".svn",
    "__pycache__", ".venv", "venv", ".tox", "target", "out",
    ".next", ".nuxt", "coverage", ".idea", ".vscode",
}
IGNORE_SUFFIXES = (".min.js", ".bundle.js", ".map")
TEST_MARKERS = ("test", "tests", "__tests__", "spec", "e2e", "testing")

EXT_LANG = {
    ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".py": "python", ".go": "go", ".java": "java",
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


def _is_ignored(path: Path, parts: tuple[str, ...]) -> bool:
    if any(d in IGNORE_DIRS for d in parts):
        return True
    if any(str(path).endswith(s) for s in IGNORE_SUFFIXES):
        return True
    return False


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
            continue
        lang = EXT_LANG.get(path.suffix.lower())
        if lang is None:
            # still record manifests for framework detection
            if path.name in MANIFESTS:
                pass
            else:
                continue
        # skip tests for file list? keep but flag later; skip to reduce noise by default? keep.
        inv.files.append(rel)
        inv.languages[lang] = inv.languages.get(lang, 0) + 1
        count += 1
        if count >= max_files:
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
