from hypergolic.tools.path_shaping import shape_path_list_text

PATHS = (
    "src/tools/a.py\n"
    "src/tools/b.py\n"
    "src/tools/tests/test_a.py\n"
    "docs/readme.md\n"
)


def test_groups_repeated_dirs_and_leaves_singletons_inline():
    assert shape_path_list_text(PATHS) == (
        "src/tools/\na.py\nb.py\n\nsrc/tools/tests/test_a.py\ndocs/readme.md\n"
    )


def test_unique_dirs_untouched():
    text = "a/x.py\nb/y.py\nc/z.py\n"
    assert shape_path_list_text(text) == text


def test_short_runs_untouched():
    text = "src/a.py\nsrc/b.py\n"
    assert shape_path_list_text(text) == text


def test_non_path_lines_break_runs_and_pass_through():
    text = "$ grep -rl foo\n" + PATHS + "Exit code: 0"
    shaped = shape_path_list_text(text)
    assert shaped.startswith("$ grep -rl foo\n")
    assert shaped.endswith("Exit code: 0")
    assert "src/tools/\na.py" in shaped


def test_lines_with_spaces_colons_or_no_slash_untouched():
    text = "see src/a.py for details\nhttp://x.com/y\nMakefile\na.py:1:x\n"
    assert shape_path_list_text(text) == text


def test_blank_line_separates_block_from_following_text():
    shaped = shape_path_list_text("src/a.py\nsrc/b.py\nsrc/c.py\nMakefile\n")
    assert shaped == "src/\na.py\nb.py\nc.py\n\nMakefile\n"
