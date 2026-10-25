from unittest.mock import patch

import pytest

from hypergolic.cli.harness_loader import HarnessLoadError
from hypergolic.contrib.tools.reload_harness import reload_harness_tool, run_reload_harness
from hypergolic.harness.app.core import App
from hypergolic.harness.primitives.tool import ToolContext
from tests._factories import approval_of, build_session
from tests.conftest import make_project, make_session


@pytest.fixture
def ctx(broadcast) -> ToolContext:
    make_project("p-rl", path="/tmp/rl")
    make_session(project_id="p-rl", sid="s-rl")
    session = build_session(sid="s-rl", project_id="p-rl", project_path="/tmp/rl")
    return ToolContext(session=session, broadcast=broadcast, tool_id="reload_harness")


def test_reload_harness_tool_metadata():
    assert reload_harness_tool.id == "reload_harness"
    assert approval_of(reload_harness_tool) == "ALLOW"


async def test_reload_reports_counts_and_rebinds_override_pins(ctx):
    app = App()
    app.use_defaults()
    with (
        patch("hypergolic.cli.harness_loader.reload_live_harness", return_value=app),
        patch("hypergolic.contrib.tools.reload_harness.drop_live_derived_pins", return_value=["X"]) as drop,
    ):
        result = await run_reload_harness(ctx)
    assert not result.is_error
    text = result.content[0]["text"]
    assert f"{len(app.tools)} tools" in text
    assert "restart" in text
    drop.assert_called_once()


async def test_reload_failure_is_an_error_result_and_keeps_pins(ctx):
    with (
        patch(
            "hypergolic.cli.harness_loader.reload_live_harness",
            side_effect=HarnessLoadError("Configuration errors:\n  - bad role"),
        ),
        patch("hypergolic.contrib.tools.reload_harness.drop_live_derived_pins") as drop,
    ):
        result = await run_reload_harness(ctx)
    assert result.is_error
    assert "bad role" in result.content[0]["text"]
    assert "still live" in result.content[0]["text"]
    drop.assert_not_called()
