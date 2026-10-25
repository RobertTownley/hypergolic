from hypergolic.tools.hook_shaping import shape_hook_text


def test_collapses_passing_hooks_and_keeps_failures():
    text = (
        "Trailing whitespace......Passed\n"
        "Ruff check...............Failed\n"
        "- hook id: ruff\n"
        "Mypy.....(no files to check)Skipped\n"
        "Check yaml...............Passed"
    )
    assert shape_hook_text(text) == (
        "[hooks: 2 passed, 1 skipped]\nRuff check...............Failed\n- hook id: ruff"
    )


def test_collapses_progress_runs_to_last_line():
    text = "a\n" + "\n".join(f"Progress: resolved {i}, added {i}" for i in range(5)) + "\nb"
    assert shape_hook_text(text) == "a\n[4 progress lines]\nProgress: resolved 4, added 4\nb"


def test_collapses_pytest_dot_rows():
    text = "\n".join("." * 10 + f" [{i:3}%]" for i in (10, 20, 30, 40)) + "\n4 passed"
    assert shape_hook_text(text) == "[3 progress lines]\n.......... [ 40%]\n4 passed"


def test_plain_text_untouched():
    text = "file1.txt\nfile2.txt\nfile3.txt"
    assert shape_hook_text(text) == text
