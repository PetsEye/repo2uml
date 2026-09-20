"""Real-repo snapshot corpus (opt-in, needs network).

    REPO2UML_CORPUS=1 python -m pytest tests/test_corpus.py -q      # compare
    UPDATE_SNAPSHOTS=1 REPO2UML_CORPUS=1 python -m pytest tests/test_corpus.py -q  # re-baseline

Repos are pinned to commit SHAs (fetched as tarballs) so snapshots are
reproducible — live-main would drift under us whenever upstream merges.
Bump a SHA in CORPUS deliberately + review the diff when you want to move.

Compares architecture.puml bytes + resolution stats against committed
snapshots under tests/snapshots/. Any behavior change shows up as a diff
for human review.
"""
import json
import os
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import pytest

from repo2uml import cli

pytestmark = pytest.mark.skipif(
    not os.environ.get("REPO2UML_CORPUS"), reason="opt-in network corpus"
)

# (repo, pinned sha) — refresh deliberately, never implicitly
CORPUS = [
    ("expressjs/express", "9a34acf03cb818ff3f8bc40e44176e277a25cbb9"),
    ("pallets/flask", "d73fa1cdcbd8b1465c151db8924ba58b1dd14e35"),
    ("ahmedkhaleel2004/gitdiagram", "69c98790be9b2bc1cc5834cf924287c5e7fdc55b"),
]

SNAP = Path(__file__).parent / "snapshots"


def fetch_at_sha(repo: str, sha: str, dest: Path) -> Path:
    url = f"https://codeload.github.com/{repo}/tar.gz/{sha}"
    tmp = dest / "repo.tar.gz"
    urllib.request.urlretrieve(url, tmp)
    with tarfile.open(tmp, "r:gz") as tf:
        tf.extractall(dest, filter="data")
    tmp.unlink()
    inner = [x for x in dest.iterdir() if x.name != "repo.tar.gz"]
    assert len(inner) == 1 and inner[0].is_dir()
    return inner[0]


@pytest.mark.parametrize("repo,sha", CORPUS)
def test_corpus_snapshot(tmp_path, repo, sha):
    slug = repo.replace("/", "__")
    work = tmp_path / "src"
    work.mkdir()
    root = fetch_at_sha(repo, sha, work)
    out = tmp_path / slug
    rc = cli.main([str(root), "--out", str(out), "--no-render"])
    assert rc == 0
    puml = (out / "architecture.puml").read_text()
    ir = json.loads((out / "architecture.json").read_text())
    stats = ir["stats"]
    snap_puml = SNAP / f"{slug}.puml"
    snap_stats = SNAP / f"{slug}.stats.json"
    if os.environ.get("UPDATE_SNAPSHOTS"):
        SNAP.mkdir(exist_ok=True)
        snap_puml.write_text(puml)
        snap_stats.write_text(json.dumps(stats, indent=2, sort_keys=True))
        (SNAP / "corpus.json").write_text(
            json.dumps({r: s for r, s in CORPUS}, indent=2))
        pytest.skip(f"recorded snapshots for {repo}")
    assert snap_puml.exists(), f"no snapshot for {repo}; run with UPDATE_SNAPSHOTS=1"
    assert puml == snap_puml.read_text(), f"diagram drift for {repo}"
    old = json.loads(snap_stats.read_text())
    # absolute resolved edges must never decrease; rate may dip when we
    # capture a LARGER import universe (more honest denominator), so it
    # gets a tolerance band instead of a hard floor
    assert stats["resolved"] >= old["resolved"], (
        f"resolved edges regressed for {repo}: {stats['resolved']} < {old['resolved']}"
    )
    assert stats["resolution_rate"] >= old["resolution_rate"] - 0.15, (
        f"resolution regressed for {repo}: {stats['resolution_rate']} < {old['resolution_rate']}"
    )
