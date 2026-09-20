"""Real-repo snapshot corpus (opt-in, needs network).

    REPO2UML_CORPUS=1 python -m pytest tests/test_corpus.py -q      # compare
    UPDATE_SNAPSHOTS=1 REPO2UML_CORPUS=1 python -m pytest tests/test_corpus.py -q  # re-baseline

Compares architecture.puml bytes + resolution stats against committed
snapshots under tests/snapshots/. Any behavior change shows up as a diff
for human review.
"""
import json
import os
from pathlib import Path

import pytest

from repo2uml import cli

pytestmark = pytest.mark.skipif(
    not os.environ.get("REPO2UML_CORPUS"), reason="opt-in network corpus"
)

CORPUS = [
    "expressjs/express",
    "pallets/flask",
    "ahmedkhaleel2004/gitdiagram",
]

SNAP = Path(__file__).parent / "snapshots"


@pytest.mark.parametrize("repo", CORPUS)
def test_corpus_snapshot(tmp_path, repo):
    slug = repo.replace("/", "__")
    out = tmp_path / slug
    rc = cli.main([repo, "--out", str(out), "--no-render"])
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
