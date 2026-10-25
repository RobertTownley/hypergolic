import sys
import threading
from unittest.mock import patch

import pytest

from hypergolic.contrib.tools.restart import (
    _restart_after_delay,
    restart_tool,
    run_restart,
)
from hypergolic.enums import SessionStatus
from hypergolic.harness.primitives.tool import ToolContext
from tests._factories import approval_of, build_session
from tests.conftest import make_project, make_session


@pytest.fixture
def ctx(broadcast) -> ToolContext:
    make_project("p-rs", path="/tmp/rs")
    make_session(project_id="p-rs", sid="s-rs")
    session = build_session(sid="s-rs", project_id="p-rs", project_path="/tmp/rs")
    return ToolContext(session=session, broadcast=broadcast, tool_id="restart")


def test_restart_tool_metadata():
    assert restart_tool.id == "restart"
    assert approval_of(restart_tool) == "REQUIRE_APPROVAL"


@pytest.mark.parametrize("delay, expected_sleep", [(0.0, 0.0), (None, 1.0)])
def test_restart_after_delay_sleeps_then_execv(delay, expected_sleep):
    with (
        patch("time.sleep") as mock_sleep,
        patch("hypergolic.contrib.tools.restart.os.execv") as mock_execv,
    ):
        if delay is None:
            _restart_after_delay("s-rs")
        else:
            _restart_after_delay("s-rs", delay=delay)

    mock_sleep.assert_called_once_with(expected_sleep)
    mock_execv.assert_called_once()
    exe_arg, args_list = mock_execv.call_args[0]
    assert exe_arg == sys.executable
    assert args_list[0] == sys.executable
    assert args_list[1:] == sys.argv


def test_restart_after_delay_drops_the_resume_flag_when_exec_fails():
    with (
        patch("time.sleep"),
        patch(
            "hypergolic.contrib.tools.restart.os.execv",
            side_effect=OSError("no exec"),
        ),
        patch("hypergolic.contrib.tools.restart.set_session_resume") as mock_set,
        pytest.raises(OSError),
    ):
        _restart_after_delay("s-rs")

    mock_set.assert_called_once_with("s-rs", False)


async def test_run_restart_success_sets_idle_and_starts_thread(ctx):
    delay_ran = threading.Event()
    with (
        patch("hypergolic.contrib.tools.restart.set_session_status") as mock_status,
        patch("hypergolic.contrib.tools.restart.set_session_resume") as mock_resume,
        patch(
            "hypergolic.contrib.tools.restart._restart_after_delay",
            side_effect=lambda _sid: delay_ran.set(),
        ) as mock_delay,
    ):
        result = await run_restart(ctx)
        assert delay_ran.wait(timeout=2.0)

    assert not result.is_error
    assert "restart" in result.content[0]["text"].lower()
    mock_status.assert_called_once_with("s-rs", SessionStatus.IDLE)
    mock_resume.assert_called_once_with("s-rs", True)
    mock_delay.assert_called_once()
