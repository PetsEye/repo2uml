"""Crash corpus: hostile inputs must exit cleanly, never traceback.

Tests marked xfail(strict=True) document CURRENT crashes — Phase 1 fixes
them, at which point the marker is removed.
"""
import os
import stat

import pytest

from repo2uml import cli, inventory


def test_empty_dir_returns_2(tmp_path):
    assert cli.main([str(tmp_path), "--out", str(tmp_path / "out"), "--no-render"]) == 2


def test_no_supported_files_returns_2(tmp_path):
    (tmp_path / "README.md").write_text("# hi\n")
    assert cli.main([str(tmp_path), "--out", str(tmp_path / "out"), "--no-render"]) == 2


def test_huge_minified_file_no_hang(tmp_path):
    (tmp_path / "bundle.js").write_text("var a=" + "1," * 600_000 + "2;\n")
    rc = cli.main([str(tmp_path), "--out", str(tmp_path / "out"), "--no-render"])
    assert rc == 0


def test_latin1_source_still_resolves(tmp_path):
    (tmp_path / "b.py").write_text("X = 1\n")
    (tmp_path / "a.py").write_bytes("# caf\xe9 comment\nfrom b import X\n".encode("latin-1"))
    rc = cli.main([str(tmp_path), "--out", str(tmp_path / "out"), "--no-render"])
    assert rc == 0
    import json
    ir = json.loads((tmp_path / "out" / "architecture.json").read_text())
    assert ["a.py", "b.py"] in ir["edges"] or ["b.py", "a.py"] in ir["edges"] or ir["stats"]["resolved"] >= 1


def test_unreadable_file_skipped(tmp_path):
    (tmp_path / "good.py").write_text("X = 1\n")
    bad = tmp_path / "bad.py"
    bad.write_text("Y = 2\n")
    os.chmod(bad, 0)
    try:
        rc = cli.main([str(tmp_path), "--out", str(tmp_path / "out"), "--no-render"])
    finally:
        os.chmod(bad, stat.S_IRUSR | stat.S_IWUSR)
    assert rc == 0


def test_symlink_loop_terminates(tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "a.py").write_text("X = 1\n")
    os.symlink(tmp_path / "real", tmp_path / "real" / "loop", target_is_directory=True)
    inv = inventory.scan(tmp_path)
    assert any(str(f) == "real/a.py" for f in inv.files)


def test_bad_source_clean_exit(tmp_path, capsys):
    rc = cli.main(["not-a-repo!!!", "--out", str(tmp_path / "out"), "--no-render"])
    assert rc == 2
    assert "error" in capsys.readouterr().err


def test_unwritable_out_clean_exit(tmp_path):
    (tmp_path / "blocker").write_text("x")
    (tmp_path / "a.py").write_text("X = 1\n")
    rc = cli.main([str(tmp_path), "--out", str(tmp_path / "blocker" / "out"), "--no-render"])
    assert rc != 0
