"""The host repairs `edit` heredocs only where the hunk grammar makes the
agent's intent certain; everything else reaches the shell as written."""

import pytest

from hypergolic.sandbox.tool.heredoc import prepare_edit_heredocs

BODY = "<<<<\nx\n====\ny\n>>>>\n"


@pytest.mark.parametrize(
    "command",
    [
        "edit a.py <<'EOF'\n" + BODY + "EOF\n",  # already safe
        "cat > f <<EOF\n<<<<\nEOF\n>>>>\nEOF\n",  # not edit: no grammar to lean on
        "python3 - <<EOF\nprint(1)\nEOF\n",
        "edit a.py <<'EOF'\n<<<<\nx\n",  # no terminator at all: shell reports it
        "git edit <<EOF\nx\nEOF\n",  # `edit` as an argument, not the command
        "echo edit a <<EOF\nEOF\n",
        "edit a.py <<'EOF'\n" + BODY + "EOF\necho EOF\n",  # delimiter after the body
        "ls; echo done",
    ],
)
def test_untouched(command):
    assert prepare_edit_heredocs(command) == (command, [])


def test_unquoted_delimiter_is_quoted():
    out, notes = prepare_edit_heredocs("edit a.py <<EOF\n<<<<\nx\n====\ny $HOME\n>>>>\nEOF\n")
    assert out.startswith("edit a.py <<'EOF'\n")
    assert out.endswith("y $HOME\n>>>>\nEOF\n")
    assert len(notes) == 1 and "quoted" in notes[0]


def test_double_quoted_delimiter_counts_as_quoted():
    command = 'edit a.py <<"EOF"\n' + BODY + "EOF\n"
    assert prepare_edit_heredocs(command) == (command, [])


@pytest.mark.parametrize("where", ["old", "new"])
def test_delimiter_inside_hunk_gets_fresh_delimiter(where):
    old = "cat <<'EOF'\nfoo\nEOF" if where == "old" else "x"
    new = "cat <<'EOF'\nbar\nEOF" if where == "new" else "y"
    command = f"cd /app && edit doc.md <<'EOF'\n<<<<\n{old}\n====\n{new}\n>>>>\nEOF\necho done"
    out, notes = prepare_edit_heredocs(command)
    assert out == f"cd /app && edit doc.md <<'HG_EOF'\n<<<<\n{old}\n====\n{new}\n>>>>\nHG_EOF\necho done"
    assert len(notes) == 1 and "HG_EOF" in notes[0]


def test_fresh_delimiter_avoids_body_text():
    command = "edit a <<'EOF'\n<<<<\nEOF\nHG_EOF\n====\ny\n>>>>\nEOF\n"
    out, _ = prepare_edit_heredocs(command)
    assert out.startswith("edit a <<'HG_EOF2'\n") and out.endswith(">>>>\nHG_EOF2\n")


def test_dash_form_keeps_tab_indent():
    command = "\tedit a.py <<-EOF\n\t<<<<\n\tEOF\n\t====\n\ty\n\t>>>>\n\tEOF\n"
    out, notes = prepare_edit_heredocs(command)
    assert out == "\tedit a.py <<-'HG_EOF'\n\t<<<<\n\tEOF\n\t====\n\ty\n\t>>>>\n\tHG_EOF\n"
    assert len(notes) == 1


def test_two_heredocs_repaired_independently():
    first = "edit a <<'EOF'\n" + BODY + "EOF\n"
    second = "edit b <<'EOF'\n<<<<\nEOF\n====\nc\n>>>>\nEOF\n"
    out, notes = prepare_edit_heredocs(first + second)
    assert out == first + "edit b <<'HG_EOF'\n<<<<\nEOF\n====\nc\n>>>>\nHG_EOF\n"
    assert len(notes) == 1


def test_path_prefixed_edit_and_options():
    command = "/usr/local/bin/edit --diff a.py <<EOF\n" + BODY + "EOF\n"
    out, notes = prepare_edit_heredocs(command)
    assert out == "/usr/local/bin/edit --diff a.py <<'EOF'\n" + BODY + "EOF\n"
    assert len(notes) == 1
