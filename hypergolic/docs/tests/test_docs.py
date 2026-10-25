from unittest.mock import patch

import pytest

from hypergolic.docs.operations import (
    list_doc_entries,
    read_doc_content,
    slug_from_filename,
    title_from_content,
)
from fastapi import HTTPException


def test_slug_from_filename_readme():
    assert slug_from_filename("README.md") == "readme"


def test_slug_from_filename_regular():
    assert slug_from_filename("getting-started.md") == "getting-started"


def test_title_from_content_with_heading():
    content = "# My Title\n\nSome text here."
    assert title_from_content(content, "anything.md") == "My Title"


def test_title_from_content_no_heading_readme():
    content = "No heading in this file at all."
    assert title_from_content(content, "README.md") == "README"


def test_title_from_content_no_heading_regular():
    content = "No heading in this file at all."
    assert title_from_content(content, "my-doc.md") == "My Doc"


def test_list_docs_returns_entries(api_client):
    response = api_client.get("/api/docs/list")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    first = data[0]
    assert "slug" in first
    assert "title" in first
    assert "filename" in first


def test_list_docs_includes_ordered_and_extra(api_client):
    response = api_client.get("/api/docs/list")
    data = response.json()
    slugs = [entry["slug"] for entry in data]
    # Ordered docs should be present (these files exist in the real docs dir)
    assert "readme" in slugs
    assert "installation" in slugs
    # Extra discovered docs (not in DOC_ORDER) should also appear
    assert any(s not in {
        "readme", "installation", "getting-started", "configuration",
        "tools", "workflows", "workflow-reference", "advanced-usage",
    } for s in slugs)


def test_read_doc_readme(api_client):
    response = api_client.get("/api/docs/read/readme")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "readme"
    assert "content" in data
    assert len(data["content"]) > 0


def test_read_doc_regular_slug(api_client):
    response = api_client.get("/api/docs/read/installation")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "installation"
    assert "title" in data
    assert "content" in data


def test_read_doc_not_found(api_client):
    response = api_client.get("/api/docs/read/nonexistent")
    assert response.status_code == 404


def test_list_docs_missing_ordered_files(tmp_path):
    # Only create one of the ordered files
    readme = tmp_path / "README.md"
    readme.write_text("# Hello\n")
    # Create an extra file not in DOC_ORDER
    extra = tmp_path / "extra.md"
    extra.write_text("# Extra Doc\n")

    with patch("hypergolic.docs.operations.DOCS_DIR", tmp_path):
        entries = list_doc_entries()

    slugs = [e.slug for e in entries]
    # Only README.md from the ordered list should appear (others missing)
    assert "readme" in slugs
    assert "installation" not in slugs
    # Extra file should be discovered
    assert "extra" in slugs
    # README should come first (from ordered list)
    assert entries[0].slug == "readme"


def test_list_docs_skips_init_md(tmp_path):
    # Create __init__.md which should be excluded
    init_md = tmp_path / "__init__.md"
    init_md.write_text("# Init\n")
    # Create a normal extra file
    normal = tmp_path / "normal.md"
    normal.write_text("# Normal\n")

    with patch("hypergolic.docs.operations.DOCS_DIR", tmp_path):
        entries = list_doc_entries()

    filenames = [e.filename for e in entries]
    assert "__init__.md" not in filenames
    assert "normal.md" in filenames


def test_read_doc_content_path_traversal_unit(tmp_path):
    """Unit test: read_doc_content raises 403 for path traversal."""
    safe = tmp_path / "docs"
    safe.mkdir()
    (safe / "ok.md").write_text("# OK\n")

    with patch("hypergolic.docs.operations.DOCS_DIR", safe):

        with pytest.raises(HTTPException) as exc_info:
            read_doc_content("../ok")
        assert exc_info.value.status_code == 403


def test_read_doc_content_not_found_unit(tmp_path):
    """Unit test: read_doc_content raises 404 for missing file."""
    with patch("hypergolic.docs.operations.DOCS_DIR", tmp_path):

        with pytest.raises(HTTPException) as exc_info:
            read_doc_content("missing")
        assert exc_info.value.status_code == 404


def test_read_doc_content_readme_unit(tmp_path):
    """Unit test: read_doc_content correctly maps 'readme' → README.md."""
    readme = tmp_path / "README.md"
    readme.write_text("# Test Readme\nContent here.")

    with patch("hypergolic.docs.operations.DOCS_DIR", tmp_path):
        result = read_doc_content("readme")

    assert result.slug == "readme"
    assert result.title == "Test Readme"
    assert "Content here." in result.content
