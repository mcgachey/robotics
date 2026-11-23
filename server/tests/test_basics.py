import json
import os

import pytest

from server.diagnostics import parse_javac
from server.storage import atomic_write_text, valid_id, valid_java_identifier


def test_atomic_write_replaces_and_leaves_no_temp(tmp_path):
    p = tmp_path / "a" / "f.json"
    atomic_write_text(p, "one")
    atomic_write_text(p, "two")
    assert p.read_text() == "two"
    assert [x.name for x in p.parent.iterdir()] == ["f.json"]


def test_atomic_write_failure_keeps_old_content(tmp_path, monkeypatch):
    p = tmp_path / "f"
    atomic_write_text(p, "old")
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        atomic_write_text(p, "new")
    monkeypatch.undo()
    assert p.read_text() == "old"
    assert [x.name for x in tmp_path.iterdir()] == ["f"]


def test_ids():
    assert valid_id("lesson0") and valid_id("s0a1b2c3d")
    for bad in ["", "../x", "A", "a_b", "a/b", ".hidden", None, 5]:
        assert not valid_id(bad)
    assert valid_java_identifier("HelloWorld") and not valid_java_identifier("class")
    assert not valid_java_identifier("1abc")


def test_parse_javac_missing_semicolon():
    out = ("HelloWorld.java:6: error: ';' expected\n"
           "        robot.log(\"x\")\n"
           "                       ^\n"
           "1 error\n")
    (d,) = parse_javac(out)
    assert (d["file"], d["line"], d["column"], d["severity"]) == ("HelloWorld.java", 6, 24, "error")
    assert "semicolon" in d["message"].lower()
    assert d["javac"] == "';' expected" and "robot.log" in d["raw"]


def test_parse_javac_cannot_find_symbol():
    out = ("/tmp/x/src/HelloWorld.java:5: error: cannot find symbol\n"
           "        robt.log(\"x\");\n"
           "        ^\n"
           "  symbol:   variable robt\n"
           "  location: class HelloWorld\n"
           "1 error\n")
    (d,) = parse_javac(out)
    assert d["file"] == "HelloWorld.java" and "robt" in d["message"]
