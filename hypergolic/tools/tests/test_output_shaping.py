from hypergolic.harness.app import state
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.tools.output_shaping import shape_tool_output

GREP = "src/a.py:1:x = 1\nsrc/a.py:9:y = 2\nsrc/b.py:3:z = 3\n"
PATHS = "src/a.py\nsrc/b.py\nsrc/c.py\n"


def test_applies_grep_and_path_shaping():
    text = shape_tool_output(ToolResult.text(GREP + "--\n" + PATHS)).content[0]["text"]
    assert "src/a.py\n1:x = 1" in text
    assert "src/\na.py\nb.py\nc.py" in text


def test_preserves_flags_and_meta():
    shaped = shape_tool_output(ToolResult.text(GREP, is_error=True, meta={"k": "v"}))
    assert shaped.is_error
    assert shaped.meta == {"k": "v"}


def test_result_unchanged_when_disabled():
    prior = state._current_app
    set_app(App(shape_grep_output=False))
    try:
        result = ToolResult.text(GREP)
        assert shape_tool_output(result) is result
    finally:
        state._current_app = prior


def test_enabled_by_default():
    prior = state._current_app
    set_app(App())
    try:
        assert shape_tool_output(ToolResult.text(GREP)).content[0]["text"] != GREP
    finally:
        state._current_app = prior
