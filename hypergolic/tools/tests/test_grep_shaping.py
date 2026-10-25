from hypergolic.tools.grep_shaping import shape_grep_text

GREP = (
    "src/a.py:1:x = 1\n"
    "src/a.py:9:y = 2\n"
    "src/b.py:3:z = 3\n"
)


def test_groups_repeated_paths():
    assert shape_grep_text(GREP) == (
        "src/a.py\n1:x = 1\n9:y = 2\n\nsrc/b.py\n3:z = 3\n"
    )


def test_unique_paths_untouched():
    text = "a/x.py:1:a\nb/y.py:2:b\nc/z.py:3:c\n"
    assert shape_grep_text(text) == text


def test_short_runs_untouched():
    text = "src/a.py:1:x\nsrc/a.py:2:y\n"
    assert shape_grep_text(text) == text


def test_non_match_lines_break_runs_and_pass_through():
    text = "$ grep -rn foo\n" + GREP + "Exit code: 0"
    assert "src/a.py\n1:x = 1" in shape_grep_text(text)
    assert shape_grep_text(text).startswith("$ grep -rn foo\n")
    assert shape_grep_text(text).endswith("Exit code: 0")


def test_timestamps_not_treated_as_paths():
    text = "12:34:one\n12:35:two\n12:36:three\n"
    assert shape_grep_text(text) == text
