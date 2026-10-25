"""`edit` must never write a file on a hunk it is unsure about: a zero or
ambiguous match is a hard failure that leaves the file untouched."""

import io
import subprocess
import sys
from pathlib import Path

import pytest

from hypergolic.sandbox import edit
from hypergolic.sandbox.edit import EditError, apply_hunks, parse_hunks


def hunk(old: str, new: str) -> str:
    return f"<<<<\n{old}\n====\n{new}\n>>>>\n"


def run(path: Path, stdin: str, *flags: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    rc = edit.main([*flags, str(path)], io.StringIO(stdin), out, err)
    return rc, out.getvalue(), err.getvalue()


def test_parse_many_hunks_keeps_text_verbatim():
    text = hunk("  a\n\tb", "") + hunk("x", "'q' \"r\" $z \\n")
    assert parse_hunks(text) == [("  a\n\tb", ""), ("x", "'q' \"r\" $z \\n")]


@pytest.mark.parametrize(
    "text, frag",
    [
        ("<<<<\na\n>>>>\n", ">>>> before ===="),
        ("<<<<\n====\nb\n>>>>\n", "empty find text"),
        ("<<<<\na\n====\nb\n", "unterminated"),
        ("stray\n<<<<\na\n====\nb\n>>>>\n", "outside a hunk"),
        ("<<<<\na\n<<<<\n", "inside an open hunk"),
        ("====\n", "outside a hunk"),
        ("", "no hunks"),
    ],
)
def test_parse_rejects_malformed_input(text, frag):
    with pytest.raises(EditError, match=frag):
        parse_hunks(text)


def test_apply_in_order_and_delete():
    out = apply_hunks("a\nb\nc\n", [("b\n", ""), ("a\nc", "a\nC")])
    assert out == "a\nC\n"


def test_apply_refuses_zero_or_ambiguous_matches():
    with pytest.raises(EditError, match="hunk 1: no match"):
        apply_hunks("a\n", [("z", "y")])
    with pytest.raises(EditError, match="hunk 2: 2 matches"):
        apply_hunks("a\nb\nb\n", [("a", "A"), ("b", "B")])
    assert apply_hunks("a\nb\nb\n", [("b", "B")], all_=True) == "a\nB\nB\n"


def test_no_match_diagnostic_points_at_the_divergent_line():
    with pytest.raises(EditError) as exc:
        apply_hunks("one\ntwo\nthree\n", [("one\ntwo\nfour", "")])
    assert "lines 1-2 match the first 2 of 3" in str(exc.value)
    assert "'three'" in str(exc.value) and "'four'" in str(exc.value)
    with pytest.raises(EditError, match="different whitespace at line 2"):
        apply_hunks("one\ntwo \nthree\n", [("two\nthree", "")])


def test_main_writes_only_when_every_hunk_applies(tmp_path):
    f = tmp_path / "f.txt"
    f.write_text("a\nb\n")
    rc, out, err = run(f, hunk("a", "A") + hunk("nope", "x"))
    assert rc == 1 and "hunk 2: no match" in err
    assert f.read_text() == "a\nb\n"
    rc, out, err = run(f, hunk("a", "A") + hunk("b", "B"), "--diff")
    assert rc == 0 and out.startswith(f"{f}: 2 hunks applied\n--- ") and "+A\n" in out
    assert f.read_text() == "A\nB\n"


def test_main_preserves_crlf_and_reports_missing_file(tmp_path):
    f = tmp_path / "f.txt"
    f.write_bytes(b"a\r\nb\r\n")
    rc, _, err = run(f, hunk("b", "B"))
    assert rc == 0 and f.read_bytes() == b"a\r\nB\r\n"
    rc, _, err = run(tmp_path / "missing", hunk("a", "b"))
    assert rc == 1 and "missing" in err


def test_runs_standalone_without_the_package(tmp_path):
    """The sandbox wrapper execs this file directly with hg-python, where
    `hypergolic` is a read-only mount and not importable."""
    f = tmp_path / "f.txt"
    f.write_text("hello\n")
    proc = subprocess.run(
        [sys.executable, "-I", edit.__file__, str(f)],
        input=hunk("hello", "bye"), capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert f.read_text() == "bye\n"
