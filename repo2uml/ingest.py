"""Source ingestion: local path, GitHub URL, or org/repo short form."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

GITHUB_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)?"
    r"(?P<org>[A-Za-z0-9_.\-]+)/(?P<repo>[A-Za-z0-9_.\-]+?)(?:\.git)?/?$"
)

NET_TIMEOUT = 60  # seconds per network operation
CLONE_TIMEOUT = 300  # git clone can be slow on huge repos
TARBALL_MAX_BYTES = 500 * 1024 * 1024  # refuse absurd downloads


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
        check=True, capture_output=True, text=True, timeout=CLONE_TIMEOUT,
    )
    return dest


def _download_capped(url: str, tmp_path: str) -> None:
    """Download with timeout + size cap (urlretrieve has neither)."""
    with urllib.request.urlopen(url, timeout=NET_TIMEOUT) as r, open(tmp_path, "wb") as f:
        n = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            n += len(chunk)
            if n > TARBALL_MAX_BYTES:
                raise RuntimeError(f"tarball exceeds {TARBALL_MAX_BYTES // 1024 // 1024}MB cap")
            f.write(chunk)


def _tarball(org: str, repo: str, dest: Path) -> Path:
    errors = []
    for branch in ("main", "master"):
        url = f"https://codeload.github.com/{org}/{repo}/tar.gz/{branch}"
        fd, tmp_path = tempfile.mkstemp(suffix=".tar.gz")
        try:
            with open(fd, "wb"):
                pass
            _download_capped(url, tmp_path)
            with tarfile.open(tmp_path, "r:gz") as tf:
                # filter= needs 3.12+; the package requires 3.9+
                kw = {"filter": "data"} if sys.version_info >= (3, 12) else {}
                tf.extractall(dest, **kw)
            inner = list(dest.iterdir())
            # codeload wraps in org-repo-branch/; flatten one level
            if len(inner) == 1 and inner[0].is_dir():
                for child in inner[0].iterdir():
                    shutil.move(str(child), str(dest / child.name))
                shutil.rmtree(inner[0], ignore_errors=True)
            return dest
        except (urllib.error.URLError, tarfile.TarError, OSError, RuntimeError) as e:
            errors.append(f"{branch}: {e}")
            shutil.rmtree(dest, ignore_errors=True)
            dest.mkdir(parents=True, exist_ok=True)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    raise RuntimeError(f"Could not fetch tarball for {org}/{repo} ({'; '.join(errors)})")


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
    dest = Path(tempfile.mkdtemp(prefix=f"repo2uml-{repo}-", dir=str(base)))
    # clone into subdir to keep mkdtemp wrapper for easy cleanup
    target = dest / repo
    try:
        if _git_available():
            try:
                return _clone_shallow(org, repo, target), True
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
                pass  # fall back to tarball (private/no git/slow net)
        return _tarball(org, repo, target), True
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
