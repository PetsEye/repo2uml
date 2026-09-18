"""Source ingestion: local path, GitHub URL, or org/repo short form."""
from __future__ import annotations

import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

GITHUB_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)?"
    r"(?P<org>[A-Za-z0-9_.\-]+)/(?P<repo>[A-Za-z0-9_.\-]+?)(?:\.git)?/?$"
)


def parse_github(source: str) -> tuple[str, str] | None:
    m = GITHUB_RE.match(source.strip())
    if not m:
        return None
    return m.group("org"), m.group("repo")


def _git_available() -> bool:
    return shutil.which("git") is not None


def _clone_shallow(org: str, repo: str, dest: Path) -> Path:
    url = f"https://github.com/{org}/{repo}.git"
    subprocess.run(
        ["git", "clone", "--depth", "1", url, str(dest)],
        check=True, capture_output=True, text=True,
    )
    return dest


def _tarball(org: str, repo: str, dest: Path) -> Path:
    for branch in ("main", "master"):
        url = f"https://codeload.github.com/{org}/{repo}/tar.gz/{branch}"
        try:
            with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
                tmp_path = tmp.name
            urllib.request.urlretrieve(url, tmp_path)
            with tarfile.open(tmp_path, "r:gz") as tf:
                tf.extractall(dest, filter="data")
            inner = list(dest.iterdir())
            # codeload wraps in org-repo-branch/; flatten one level
            if len(inner) == 1 and inner[0].is_dir():
                for child in inner[0].iterdir():
                    shutil.move(str(child), str(dest / child.name))
                inner[0].rmdir()
            Path(tmp_path).unlink(missing_ok=True)
            return dest
        except Exception:
            continue
    raise RuntimeError(f"Could not fetch tarball for {org}/{repo} (tried main/master)")


def resolve_source(source: str, workdir: Path | None = None) -> tuple[Path, bool]:
    """Return (repo_root, is_temp). Caller removes temp dir if is_temp."""
    p = Path(source).expanduser()
    if p.exists() and p.is_dir():
        return p.resolve(), False

    parsed = parse_github(source)
    if parsed is None:
        raise ValueError(
            f"Unknown source '{source}'. Use a local dir, "
            "https://github.com/org/repo, or org/repo."
        )
    org, repo = parsed
    base = workdir or Path(tempfile.gettempdir())
    dest = Path(tempfile.mkdtemp(prefix=f"ghubuml-{repo}-", dir=str(base)))
    # clone into subdir to keep mkdtemp wrapper for easy cleanup
    target = dest / repo
    try:
        if _git_available():
            try:
                return _clone_shallow(org, repo, target), True
            except subprocess.CalledProcessError:
                pass  # fall back to tarball (private/no git)
        return _tarball(org, repo, target), True
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
