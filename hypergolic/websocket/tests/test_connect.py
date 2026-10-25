from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from hypergolic.websocket.connect import handle_connect
from hypergolic.websocket.schemas import ConnectMessage
from hypergolic.websocket.tests._helpers import make_deps
from hypergolic.workflows.engine import WorkflowError


@pytest.fixture(autouse=True)
def _stub_persistence():
    with (
        patch("hypergolic.websocket.connect.persist_messages", new_callable=AsyncMock) as pm,
        patch("hypergolic.websocket.connect.maybe_generate_description", new_callable=AsyncMock),
    ):
        yield pm


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.load_session")
async def test_message_persisted_before_turn(mock_load, mock_run, _stub_persistence):
    notify, broadcast, approval_callback, cancel = make_deps()
    session = MagicMock()
    session.id = "s-1"
    mock_load.return_value = session

    order: list[str] = []
    _stub_persistence.side_effect = lambda **kw: order.append("persist")
    mock_run.side_effect = lambda *a, **kw: order.append("run")

    req = ConnectMessage(message="hello", session_id="s-1")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    assert order == ["persist", "run"]
    persisted = _stub_persistence.call_args.kwargs["messages"][0]
    assert persisted["role"] == "user"
    # The turn must not re-persist: message arg is None.
    assert mock_run.call_args.args[1] is None


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.load_session")
async def test_existing_session(mock_load, mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()
    session = MagicMock()
    session.id = "s-1"
    mock_load.return_value = session

    req = ConnectMessage(message="hello", session_id="s-1")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    mock_load.assert_called_once_with("s-1")
    mock_run.assert_called_once()


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.create_session")
async def test_new_session(mock_create, mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()
    session = MagicMock()
    session.id = "s-new"
    mock_create.return_value = session

    req = ConnectMessage(message="hello", project_id="p-1", base_branch="main")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    mock_create.assert_called_once()
    mock_run.assert_called_once()


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
async def test_new_session_missing_project_id(mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()

    req = ConnectMessage(message="hello")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    sent = notify.call_args[0][0]
    assert sent["type"] == "error"
    assert "project_id" in sent["detail"]
    mock_run.assert_not_called()


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
async def test_new_session_missing_base_branch(mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()

    req = ConnectMessage(message="hello", project_id="p-1")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    sent = notify.call_args[0][0]
    assert sent["type"] == "error"
    assert "base_branch" in sent["detail"]
    mock_run.assert_not_called()


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.activate_workflow", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.load_session")
async def test_with_workflow(mock_load, mock_wf, mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()
    session = MagicMock()
    session.id = "s-1"
    mock_load.return_value = session

    req = ConnectMessage(message="go", session_id="s-1", workflow_id="wf-1")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    mock_wf.assert_called_once()
    mock_run.assert_called_once()


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.activate_workflow", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.load_session")
async def test_workflow_error(mock_load, mock_wf, mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()
    session = MagicMock()
    session.id = "s-1"
    mock_load.return_value = session
    mock_wf.side_effect = WorkflowError("not found")

    req = ConnectMessage(message="go", session_id="s-1", workflow_id="wf-bad")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    sent = notify.call_args[0][0]
    assert sent["type"] == "error"
    assert "not found" in sent["detail"]
    mock_run.assert_not_called()


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.load_session")
@patch("hypergolic.websocket.connect.set_session_status_and_broadcast", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.persist_error_message")
@patch("hypergolic.websocket.connect.persist_error")
async def test_error_persisted(mock_perr, mock_perr_msg, mock_status, mock_load, mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()
    mock_load.side_effect = RuntimeError("db fail")

    req = ConnectMessage(message="go", session_id="s-1")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    sent = notify.call_args[0][0]
    assert sent["type"] == "error"
    assert "db fail" in sent["detail"]


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.create_session")
@patch("hypergolic.websocket.connect.set_session_status_and_broadcast", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.persist_error_message")
@patch("hypergolic.websocket.connect.persist_error")
async def test_error_with_session_id_persists(mock_perr, mock_perr_msg, mock_status, mock_create, mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()
    session = MagicMock()
    session.id = "s-1"
    mock_create.return_value = session
    mock_run.side_effect = RuntimeError("turn fail")

    req = ConnectMessage(message="go", project_id="p-1", base_branch="main")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)

    mock_status.assert_called_once()
    mock_perr_msg.assert_called_once()
    mock_perr.assert_called_once()


@patch("hypergolic.websocket.connect.run_session_turn", new_callable=AsyncMock)
@patch("hypergolic.websocket.connect.load_session")
async def test_error_send_fails(mock_load, mock_run):
    notify, broadcast, approval_callback, cancel = make_deps()
    mock_load.side_effect = RuntimeError("fail")
    notify.side_effect = Exception("ws closed")

    req = ConnectMessage(message="go", session_id="s-1")
    await handle_connect(req, cancel, notify, broadcast, approval_callback)
