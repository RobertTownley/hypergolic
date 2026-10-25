"""Tests for hypergolic.files.search."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from hypergolic.files.search import (
    _parse_search_output,
    _search_contents_python,
    _search_contents_rg,
    search_file_contents,
    search_file_names,
)

SEARCH = "hypergolic.files.search"


def _run(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout=stdout)


@pytest.fixture
def mock_run():
    with patch(f"{SEARCH}.subprocess.run") as m:
        yield m


# ── search_file_names ───────────────────────────────────────────────


class TestSearchFileNames:
    def test_filters_by_all_query_parts(self, mock_run, tmp_path):
        mock_run.return_value = _run("src/app.py\nsrc/main.py\ntest/test_app.py\n")
        results = search_file_names("app", tmp_path, True, False, 50)
        assert len(results) == 2
        assert all("app" in m.path.lower() for m in results)

    def test_multi_word_query_requires_all_parts(self, mock_run, tmp_path):
        mock_run.return_value = _run("src/user_service.py\nsrc/user.py\ntest/service_test.py\n")
        results = search_file_names("user service", tmp_path, True, False, 50)
        assert [m.path for m in results] == ["src/user_service.py"]

    def test_respects_max_results(self, mock_run, tmp_path):
        mock_run.return_value = _run("\n".join(f"f{i}.py" for i in range(100)))
        assert len(search_file_names("f", tmp_path, True, False, 5)) == 5

    @pytest.mark.parametrize(
        "include_hidden,expected_paths",
        [
            (False, ["src/visible.py"]),
            (True, ["src/visible.py", ".hidden/secret.py"]),
        ],
        ids=["skip-hidden", "include-hidden"],
    )
    def test_hidden_handling(self, mock_run, tmp_path, include_hidden, expected_paths):
        mock_run.return_value = _run(".hidden/secret.py\nsrc/visible.py\n")
        results = search_file_names("py", tmp_path, True, include_hidden, 50)
        assert sorted(m.path for m in results) == sorted(expected_paths)

    @pytest.mark.parametrize(
        "exc",
        [FileNotFoundError, subprocess.TimeoutExpired("git", 10), subprocess.CalledProcessError(1, "git")],
        ids=["missing-binary", "timeout", "non-zero-exit"],
    )
    def test_returns_empty_on_subprocess_failure(self, mock_run, tmp_path, exc):
        mock_run.side_effect = exc
        assert search_file_names("x", tmp_path, True, False, 50) == []

    def test_omits_exclude_standard_when_not_respecting_gitignore(self, mock_run, tmp_path):
        mock_run.return_value = _run()
        search_file_names("x", tmp_path, False, False, 50)
        assert "--exclude-standard" not in mock_run.call_args[0][0]

    def test_skips_blank_lines(self, mock_run, tmp_path):
        mock_run.return_value = _run("\n  \nsrc/a.py\n")
        assert len(search_file_names("a", tmp_path, True, False, 50)) == 1

    def test_sorts_basename_matches_first(self, mock_run, tmp_path):
        mock_run.return_value = _run("deep/nested/path/app.py\napp.py\n")
        results = search_file_names("app", tmp_path, True, False, 50)
        assert results[0].path == "app.py"


# ── _parse_search_output ────────────────────────────────────────────


class TestParseSearchOutput:
    def test_parses_path_line_text_triples(self):
        stdout = "/repo/src/a.py:10:hello world\n/repo/src/b.py:20:foo bar\n"
        results = _parse_search_output(stdout, Path("/repo"), 50)
        assert len(results) == 2
        assert results[0].path == "src/a.py"
        assert results[0].line == 10
        assert results[0].text == "hello world"

    def test_keeps_path_when_not_relative_to_root(self):
        results = _parse_search_output("other/a.py:5:text\n", Path("/repo"), 50)
        assert results[0].path == "other/a.py"

    def test_skips_empty_lines_and_separators(self):
        results = _parse_search_output("\n--\n/repo/a.py:1:x\n", Path("/repo"), 50)
        assert len(results) == 1

    def test_skips_malformed_lines(self):
        results = _parse_search_output("just-a-path\n/repo/a.py:1:ok\n", Path("/repo"), 50)
        assert len(results) == 1

    def test_respects_max_results(self):
        stdout = "\n".join(f"/repo/f{i}.py:{i}:text" for i in range(100))
        assert len(_parse_search_output(stdout, Path("/repo"), 3)) == 3

    def test_skips_lines_with_non_integer_line_number(self):
        results = _parse_search_output("/repo/a.py:abc:text\n", Path("/repo"), 50)
        assert results == []

    def test_truncates_text_to_200_chars(self):
        stdout = f"/repo/a.py:1:{'x' * 300}\n"
        results = _parse_search_output(stdout, Path("/repo"), 50)
        assert results[0].text is not None
        assert len(results[0].text) == 200


# ── _search_contents_rg ────────────────────────────────────────────


class TestSearchContentsRg:
    def test_parses_ripgrep_output(self, mock_run, tmp_path):
        mock_run.return_value = _run(f"{tmp_path}/a.py:1:match line\n")
        assert len(_search_contents_rg("match", tmp_path, True, False, 50)) == 1

    def test_includes_no_ignore_and_hidden_flags(self, mock_run, tmp_path):
        mock_run.return_value = _run()
        _search_contents_rg("q", tmp_path, False, True, 50)
        cmd = mock_run.call_args[0][0]
        assert "--no-ignore" in cmd and "--hidden" in cmd

    def test_returns_empty_when_rg_errors(self, mock_run, tmp_path):
        mock_run.return_value = _run(returncode=2)
        assert _search_contents_rg("q", tmp_path, True, False, 50) == []

    @pytest.mark.parametrize(
        "exc",
        [FileNotFoundError, subprocess.TimeoutExpired("rg", 10)],
        ids=["missing-binary", "timeout"],
    )
    def test_returns_empty_on_subprocess_failure(self, mock_run, tmp_path, exc):
        mock_run.side_effect = exc
        assert _search_contents_rg("q", tmp_path, True, False, 50) == []


# ── _search_contents_python ─────────────────────────────────────────


class TestSearchContentsPython:
    def test_finds_matching_line(self, tmp_path):
        (tmp_path / "a.py").write_text("hello world\n")
        results = _search_contents_python("hello", tmp_path, True, False, 50)
        assert results and results[0].text == "hello world"

    def test_returns_empty_when_no_match(self, tmp_path):
        (tmp_path / "a.py").write_text("nothing here\n")
        assert _search_contents_python("zzz", tmp_path, True, False, 50) == []


# ── search_file_contents (dispatch) ────────────────────────────────


class TestSearchFileContentsDispatch:
    def test_uses_ripgrep_when_available(self, tmp_path):
        with (
            patch(f"{SEARCH}.has_ripgrep", return_value=True),
            patch(f"{SEARCH}._search_contents_rg", return_value=[]) as m,
        ):
            search_file_contents("q", tmp_path, True, False, 50)
        m.assert_called_once()

    def test_falls_back_to_python_when_ripgrep_missing(self, tmp_path):
        with (
            patch(f"{SEARCH}.has_ripgrep", return_value=False),
            patch(f"{SEARCH}._search_contents_python", return_value=[]) as m,
        ):
            search_file_contents("q", tmp_path, True, False, 50)
        m.assert_called_once()
