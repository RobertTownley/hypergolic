"""Tests for hypergolic.files.schemas."""

from hypergolic.files.schemas import (
    FileNode,
    FileSearchMatch,
    FileSearchRequest,
    FileSearchResponse,
)


def test_file_node_defaults():
    node = FileNode(name="a.py", path="a.py", is_dir=False)
    assert node.git_status is None
    assert node.children is None


def test_file_node_recursive():
    child = FileNode(name="a.py", path="src/a.py", is_dir=False, git_status="M")
    parent = FileNode(name="src", path="src", is_dir=True, children=[child])
    assert parent.children is not None
    assert parent.children[0].git_status == "M"


def test_file_search_match_optional_fields():
    m = FileSearchMatch(path="a.py")
    assert m.line is None and m.text is None


def test_file_search_request_defaults():
    req = FileSearchRequest(query="x")
    assert req.mode == "files"
    assert req.respect_gitignore is True
    assert req.include_hidden is False
    assert req.max_results == 50


def test_file_search_response_roundtrip():
    resp = FileSearchResponse(matches=[FileSearchMatch(path="a.py", line=1, text="hi")])
    assert resp.matches[0].path == "a.py"
