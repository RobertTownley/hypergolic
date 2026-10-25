from tests.conftest import make_session
from typing import Any

import json

import pytest
from starlette.testclient import TestClient

from hypergolic.api import app
from hypergolic.commands import approval_bus
from hypergolic.commands.broker.parsing import fill_stdin
from hypergolic.commands.broker.stream import EXIT_DENIED, EXIT_UNAVAILABLE, EXIT_USAGE
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision, always
from hypergolic.harness.primitives.results import CommandResult, InputSchema, ToolResult
from hypergolic.harness.primitives.tool import SANDBOX, Tool, container_domain
from hypergolic.sandbox import exec_env
from hypergolic.tools.handlers import ApprovalResponse
from hypergolic.db.models import DBToolApproval

_client = TestClient(app)


class EchoInput(InputSchema):
    text: str


def echo_command(**overrides) -> Tool:
    async def run(inp, _ctx):
        return CommandResult(stdout=f"{inp.text}\n")

    fields: dict[str, Any] = dict(
        id="echo",
        name="Echo",
        description="Echo a string back.",
        input_schema=EchoInput,
        approval=always("ALLOW"),
        run=run,
    )
    fields.update(overrides)
    return Tool(**fields)


@pytest.fixture(autouse=True)
def _clean_registries():
    exec_env.EXEC_REGISTRY.clear()
    exec_env._SESSION_TOKENS.clear()
    exec_env._TOKEN_SESSIONS.clear()
    yield
    exec_env.EXEC_REGISTRY.clear()
    exec_env._SESSION_TOKENS.clear()
    exec_env._TOKEN_SESSIONS.clear()


@pytest.fixture
def commands(monkeypatch):
    registry: dict[str, Tool] = {}
    monkeypatch.setattr("hypergolic.commands.broker.invoke.session_commands", lambda _session: registry)
    return registry


def invoke(command="echo", argv=None, token="", exec_id=None, stdin=None):
    return _client.post(
        "/broker/invoke",
        json={
            "command": command,
            "argv": argv or [],
            "cwd": "/app",
            "exec_id": exec_id,
            "stdin": stdin,
        },
        headers={"Authorization": f"Bearer {token}"},
    )


def frames(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def exited(response) -> int:
    return next(f["code"] for f in frames(response) if f["type"] == "exit")


def streamed(response, kind: str) -> str:
    return "".join(f["data"] for f in frames(response) if f["type"] == kind)


@pytest.fixture
def authorized_session(commands):
    def authorize(command=None):
        session_id = make_session(sid="s-1")
        commands["echo"] = command or echo_command()
        token = exec_env.session_token(session_id)
        exec_id = exec_env.register_exec(session_id, "echo hi && rm -rf /tmp/probe")
        return session_id, token, exec_id
    return authorize


def test_absent_token_is_rejected_before_command_resolution(commands):
    assert invoke().status_code == 401


def test_wrong_token_is_rejected(commands, authorized_session):
    _session_id, _token, exec_id = authorized_session()
    assert invoke(token="not-a-token", exec_id=exec_id).status_code == 401


def test_another_sessions_exec_id_is_rejected(commands, authorized_session):
    _own, token, _exec_id = authorized_session()
    other = make_session(sid="s-other")
    other_exec = exec_env.register_exec(other, "echo hi")
    response = invoke(token=token, exec_id=other_exec, argv=["hi"])
    assert response.status_code == 403
    assert "another session" in response.json()["detail"]


def test_stale_exec_id_is_rejected(commands, authorized_session):
    _session_id, token, exec_id = authorized_session()
    exec_env.release_exec(exec_id)
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert response.status_code == 403


def test_unresolvable_command_is_a_transport_error(commands, authorized_session):
    _session_id, token, exec_id = authorized_session()
    assert invoke("nope", token=token, exec_id=exec_id).status_code == 404


def test_advisory_command_has_nothing_to_invoke(commands, authorized_session):
    _session_id, token, exec_id = authorized_session()
    commands["echo"] = Tool(id="echo", name="Echo", description="docs only")
    assert invoke(token=token, exec_id=exec_id).status_code == 404


def test_authorized_call_streams_stdout_then_exit_zero(commands, authorized_session):
    _session_id, token, exec_id = authorized_session()
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert exited(response) == 0
    assert streamed(response, "stdout") == "hi\n"


def test_a_tool_result_handler_lands_on_the_right_stream(commands, authorized_session):
    async def run(inp, _ctx):
        return ToolResult.text(f"boom {inp.text}", is_error=True)

    _session_id, token, exec_id = authorized_session(echo_command(run=run))
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert exited(response) == 1
    assert streamed(response, "stderr") == "boom hi"


def test_a_ctx_only_handler_still_runs(commands, authorized_session):
    async def run(_ctx):
        return CommandResult(stdout="no input needed\n")

    _session_id, token, exec_id = authorized_session(echo_command(run=run))
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert exited(response) == 0
    assert streamed(response, "stdout") == "no input needed\n"


def test_stdin_fills_at_markers_before_policy_and_handler(commands, authorized_session):
    _, token, exec_id = authorized_session()
    seen: list[dict] = []
    tool = commands["echo"]
    decide = tool.approval

    def spy(ctx):
        seen.append(ctx.input.model_dump())
        return decide(ctx)

    commands["echo"] = tool.model_copy(update={"approval": spy})
    hairy = 'it\'s got "quotes" and `ticks` | pipes'
    response = invoke(argv=["@-"], token=token, exec_id=exec_id, stdin=hairy + "\n")
    assert exited(response) == 0
    assert streamed(response, "stdout") == hairy + "\n"
    assert seen == [{"text": hairy}]


def test_inline_and_bare_markers_are_both_filled():
    argv = ["--flag=@-", "@-", "untouched"]
    assert fill_stdin(argv, "v\n") == ["--flag=v", "v", "untouched"]
    assert fill_stdin(["plain"], None) == ["plain"]


def test_a_marker_without_stdin_is_a_usage_error_with_the_heredoc_recipe(commands, authorized_session):
    _, token, exec_id = authorized_session()
    response = invoke(argv=["@-"], token=token, exec_id=exec_id)
    assert exited(response) == EXIT_USAGE
    assert "heredoc" in streamed(response, "stderr")


def test_bad_arguments_exit_with_usage(commands, authorized_session):
    _session_id, token, exec_id = authorized_session()
    response = invoke(token=token, exec_id=exec_id, argv=[])
    assert exited(response) == EXIT_USAGE
    assert "echo" in streamed(response, "stderr")


def test_denial_is_an_exit_frame_not_an_http_error(commands, authorized_session):
    command = echo_command(approval=always("DENY", "not in this session"))
    _session_id, token, exec_id = authorized_session(command)
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert response.status_code == 200
    assert exited(response) == EXIT_DENIED
    assert "not in this session" in streamed(response, "stderr")


def test_a_policy_that_raises_falls_back_to_approval(commands, authorized_session):
    def broken(_ctx: ApprovalContext) -> ToolApprovalDecision:
        raise RuntimeError("bug")

    _session_id, token, exec_id = authorized_session(echo_command(approval=broken))
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert exited(response) == EXIT_DENIED


def test_handler_failure_is_reported_not_raised(commands, authorized_session):
    async def boom(_inp, _ctx):
        raise RuntimeError("exploded")

    _session_id, token, exec_id = authorized_session(echo_command(run=boom))
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert exited(response) != 0
    assert "exploded" in streamed(response, "stderr")


def test_approval_card_shows_the_full_originating_command(commands, authorized_session):
    seen: list[dict] = []

    async def callback(request):
        seen.append(request.tool_input)
        return ApprovalResponse(approved=True)

    async def broadcast(_event):
        return None

    command = echo_command(approval=always("REQUIRE_APPROVAL"))
    session_id, token, exec_id = authorized_session(command)
    approval_bus.register(session_id, callback, broadcast)
    try:
        response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    finally:
        approval_bus.unregister(session_id)

    assert exited(response) == 0
    assert seen[0]["command"] == "echo hi && rm -rf /tmp/probe"
    assert seen[0]["invocation"] == "echo hi"
    assert seen[0]["arguments"] == {"text": "hi"}


def test_a_denied_approval_short_circuits_the_chain(commands, authorized_session):
    async def callback(_request):
        return ApprovalResponse(approved=False, denial_reason="no thanks")

    async def broadcast(_event):
        return None

    command = echo_command(approval=always("REQUIRE_APPROVAL"))
    session_id, token, exec_id = authorized_session(command)
    approval_bus.register(session_id, callback, broadcast)
    try:
        response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    finally:
        approval_bus.unregister(session_id)
    assert exited(response) == EXIT_DENIED
    assert "no thanks" in streamed(response, "stderr")


def test_child_session_cannot_be_asked_and_is_refused(commands):
    parent = make_session(sid="s-parent")
    child = make_session(sid="s-child", parent_id=parent)
    commands["echo"] = echo_command(approval=always("REQUIRE_APPROVAL"))
    token = exec_env.session_token(child)
    exec_id = exec_env.register_exec(child, "echo hi")
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert exited(response) == EXIT_DENIED


def test_every_invocation_is_persisted_even_when_auto_approved(commands, authorized_session, audit_rows):
    _session_id, token, exec_id = authorized_session()
    invoke(token=token, exec_id=exec_id, argv=["hi"])
    [row] = audit_rows.of(DBToolApproval)
    assert (row.tool_name, row.approved) == ("echo", True)


def test_timeout_is_suspended_for_the_life_of_the_invocation(commands, authorized_session):
    observed: list[bool] = []

    async def run(inp, _ctx):
        observed.append(exec_env.is_timeout_suspended(exec_id))
        return CommandResult(stdout=inp.text)

    _session_id, token, exec_id = authorized_session(echo_command(run=run))
    invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert observed == [True]
    assert not exec_env.is_timeout_suspended(exec_id)


def test_a_container_domain_command_is_refused_because_it_is_not_routed(commands):
    session_id = make_session(sid="s-1")
    commands["echo"] = echo_command(domain=container_domain("dev"))
    token = exec_env.session_token(session_id)
    exec_id = exec_env.register_exec(session_id, "echo hi", container="dev")
    response = invoke(token=token, exec_id=exec_id, argv=["hi"])
    assert exited(response) == EXIT_UNAVAILABLE
    assert "does not route" in streamed(response, "stderr")


def test_only_host_commands_are_routed_today(commands):
    session_id = make_session(sid="s-1")
    commands["echo"] = echo_command(domain=container_domain("db"))
    token = exec_env.session_token(session_id)
    exec_id = exec_env.register_exec(session_id, "echo hi", container="dev")
    assert exited(invoke(token=token, exec_id=exec_id, argv=["hi"])) == EXIT_UNAVAILABLE


def test_a_sandbox_domain_command_is_refused_for_the_same_reason(commands):
    session_id = make_session(sid="s-1")
    commands["echo"] = echo_command(domain=SANDBOX)
    token = exec_env.session_token(session_id)
    exec_id = exec_env.register_exec(session_id, "echo hi", container="dev")
    assert exited(invoke(token=token, exec_id=exec_id, argv=["hi"])) == EXIT_UNAVAILABLE
