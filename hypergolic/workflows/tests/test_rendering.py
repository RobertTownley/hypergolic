"""Tests for hypergolic.workflows.rendering."""

import json

import pytest

from hypergolic.workflows.rendering import render_artifact_text


def test_render_artifact_text_basic():
    """Header carries the id + timestamp; a string value is inserted as-is."""
    result = render_artifact_text("art-1", {"summary": "All done"}, "2024-01-01T00:00:00")
    assert "# Artifact: art-1 (2024-01-01T00:00:00)" in result
    assert "All done" in result


def test_render_artifact_text_string_value_not_bolded():
    """String values are inserted as-is (no bold key heading)."""
    result = render_artifact_text("a", {"notes": "plain text"}, "ts")
    assert "plain text" in result
    # Key should NOT appear as a bolded heading for string values
    assert "**Notes:**" not in result


@pytest.mark.parametrize(
    "key, value, expected_heading",
    [
        ("items", ["x", "y"], "**Items:**"),
        ("meta_data", {"key": "val"}, "**Meta Data:**"),  # underscore -> title-cased
        ("count", 42, "**Count:**"),
        ("done", True, "**Done:**"),
    ],
)
def test_render_artifact_text_nonstring_value_bolded(key, value, expected_heading):
    """Non-string values render under a title-cased bold heading with their
    JSON-encoded value."""
    result = render_artifact_text("a", {key: value}, "ts")
    assert expected_heading in result
    assert json.dumps(value) in result


def test_render_artifact_text_multiple_keys():
    content = {"title": "Hello", "tags": ["a", "b"], "score": 99}
    result = render_artifact_text("art-x", content, "2025-01-01")
    assert "# Artifact: art-x (2025-01-01)" in result
    # All entries should appear
    assert "Hello" in result
    assert "**Tags:**" in result
    assert "**Score:**" in result


def test_render_artifact_text_empty_content():
    result = render_artifact_text("art-empty", {}, "ts")
    assert "# Artifact: art-empty (ts)" in result
    # No extra content beyond the header
    lines = [line for line in result.split("\n") if line.strip()]
    assert len(lines) == 1
