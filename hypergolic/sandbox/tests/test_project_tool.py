from unittest.mock import patch

from hypergolic.sandbox.model.containers import Container, Port
from hypergolic.sandbox.model.egress import Egress
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from hypergolic.sandbox.tool import make_project_sandbox_tool
from hypergolic.sandbox.tool.project_tool import write_compose
from tests._factories import invoke
from hypergolic.sandbox.model.sandbox import DEFAULT_SANDBOX_ID
from hypergolic.harness.primitives.tool import ToolContext
from hypergolic.harness.primitives.results import ToolResult
from hypergolic.sandbox.compose import EMPTY_BUILD_CONTEXT
from tests._factories import build_session
from tests.conftest import make_project, make_session


def _multi() -> ProjectSandbox:
    return ProjectSandbox(
        id="proj-multi",
        containers=[
            Container(id="api", image="python:3.12", expose=[Port(container=8000, name="api")]),
            Container(id="frontend", image="node:22"),
        ],
        egress=Egress.Allow(["https://pypi.org"]),
    )


def _single() -> ProjectSandbox:
    return ProjectSandbox(id="proj-single", containers=[Container(id="only", image="alpine")])


def test_multi_container_tool_exposes_required_container_enum():
    tool = make_project_sandbox_tool(_multi())
    assert tool.id == "cmd"
    assert tool.input_schema is not None
    schema = tool.input_schema.model_json_schema()
    assert set(schema["properties"]) == {"container", "command"}
    assert set(schema["required"]) == {"container", "command"}
    enum = schema["$defs"]["ContainerEnum"]["enum"]
    assert enum == ["api", "frontend"]


def test_single_container_tool_omits_container_field():
    tool = make_project_sandbox_tool(_single())
    assert tool.input_schema is not None
    schema = tool.input_schema.model_json_schema()
    assert set(schema["properties"]) == {"command"}


def test_building_tool_has_no_filesystem_side_effect(tmp_path):
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        make_project_sandbox_tool(_multi())
    assert list(tmp_path.iterdir()) == []


def test_write_compose_materializes_config(tmp_path):
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        path = write_compose(_multi())
    written = tmp_path / "proj-multi.compose.yaml"
    assert path == str(written)
    text = written.read_text()
    assert "/app:rw" in text
    assert "working_dir" not in text
    assert (tmp_path / EMPTY_BUILD_CONTEXT).is_dir()


def test_write_compose_writes_squid_conf_for_restricted_egress(tmp_path):
    sb = ProjectSandbox(
        id="proj-egress",
        containers=[Container(id="api", image="python:3.12")],
        egress=Egress.Allow(["https://pypi.org"]),
    )
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        write_compose(sb)
    conf = tmp_path / "proj-egress.squid.conf"
    assert conf.exists()
    assert "dstdomain .pypi.org" in conf.read_text()


def test_write_compose_no_squid_conf_for_allow_all(tmp_path):
    sb = ProjectSandbox(
        id="proj-open",
        containers=[Container(id="api", image="python:3.12")],
        egress=Egress.AllowAll(),
    )
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        write_compose(sb)
    assert not (tmp_path / "proj-open.squid.conf").exists()


async def test_git_commands_reach_the_sandbox_unmodified(tmp_path, broadcast):
    make_project("p1")
    sid = make_session(project_id="p1")
    sandbox = ProjectSandbox(id="proj-git", containers=[Container(id="app", image="python:3.12")])
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        tool = make_project_sandbox_tool(sandbox)
    assert tool.input_schema is not None

    seen: list[str] = []

    async def fake_run(ctx, config_path, command, *, container, workdir, timeout):
        seen.append(command)
        return ToolResult(content=[{"type": "text", "text": "ok"}])

    wt_session = build_session(
        sid=sid, project_id="p1", project_path="/tmp/p1", worktree_path="/tmp/wt/main-s"
    )
    wt_ctx = ToolContext(session=wt_session, broadcast=broadcast, tool_id="cmd")
    with (
        patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path),
        patch("hypergolic.sandbox.tool.project_tool.run_in_sandbox", side_effect=fake_run),
    ):
        first = await invoke(tool, tool.input_schema.model_validate({"command": "git status"}), wt_ctx)
        second = await invoke(tool, tool.input_schema.model_validate({"command": "gitleaks detect"}), wt_ctx)

    assert not any(r.is_error for r in (first, second))
    assert seen == ["git status", "gitleaks detect"]


async def test_edit_heredoc_is_repaired_and_the_agent_is_told(tmp_path, broadcast):
    make_project("p2")
    sid = make_session(project_id="p2")
    sandbox = ProjectSandbox(id="proj-edit", containers=[Container(id="app", image="python:3.12")])
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        tool = make_project_sandbox_tool(sandbox)
    assert tool.input_schema is not None

    seen: list[str] = []

    async def fake_run(ctx, config_path, command, *, container, workdir, timeout):
        seen.append(command)
        return ToolResult(content=[{"type": "text", "text": "ok"}])

    ctx = ToolContext(
        session=build_session(sid=sid, project_id="p2", project_path="/tmp/p2", worktree_path="/tmp/wt/p2"),
        broadcast=broadcast, tool_id="cmd",
    )
    written = "edit README.md <<'EOF'\n<<<<\nfoo\nEOF\n====\nbar\n>>>>\nEOF\n"
    with (
        patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path),
        patch("hypergolic.sandbox.tool.project_tool.run_in_sandbox", side_effect=fake_run),
    ):
        result = await invoke(tool, tool.input_schema.model_validate({"command": written}), ctx)

    assert seen == ["edit README.md <<'HG_EOF'\n<<<<\nfoo\nEOF\n====\nbar\n>>>>\nHG_EOF\n"]
    assert not result.is_error
    assert "[cmd] heredoc delimiter `EOF`" in result.content[-1]["text"]


async def test_skip_workspace_mount_container_gets_no_workdir(tmp_path, broadcast):
    make_project("p1")
    sid = make_session(project_id="p1")
    sandbox = ProjectSandbox(
        id="proj-mixed",
        containers=[
            Container(id="app", image="python:3.12"),
            Container(id="proxy", image="squid", skip_workspace_mount=True),
        ],
    )
    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        tool = make_project_sandbox_tool(sandbox)

    session = build_session(sid=sid, project_id="p1", project_path="/tmp/p1")
    ctx = ToolContext(session=session, broadcast=broadcast, tool_id="cmd")

    calls = []

    async def fake_run(ctx, config_path, command, *, container, workdir, timeout):
        calls.append((container, workdir))

        return ToolResult(content=[{"type": "text", "text": "ok"}])

    with (
        patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path),
        patch("hypergolic.sandbox.tool.project_tool.run_in_sandbox", side_effect=fake_run),
    ):
        input_schema = tool.input_schema
        assert input_schema is not None
        await invoke(tool, input_schema.model_validate({"container": "app", "command": "ls"}), ctx)
        await invoke(tool, input_schema.model_validate({"container": "proxy", "command": "ls"}), ctx)

    assert calls == [("app", "/app"), ("proxy", None)]


async def test_default_sandbox_cmd_materializes_compose_on_run(tmp_path, broadcast):
    project = make_project("p1", "P1", "/tmp/p1")
    sid = make_session(project_id="p1")

    with patch("hypergolic.sandbox.tool.project_tool.GENERATED_SANDBOX_DIR", tmp_path):
        tool = project.default_cmd_tool()
        assert tool is not None
        compose = tmp_path / f"{DEFAULT_SANDBOX_ID}.compose.yaml"
        assert not compose.exists()

        async def fake_run(ctx, config_path, command, *, container, workdir, timeout):
            return ToolResult(content=[{"type": "text", "text": "ok"}])

        session = build_session(sid=sid, project_id="p1", project_path="/tmp/p1")
        ctx = ToolContext(session=session, broadcast=broadcast, tool_id="cmd")
        assert tool.input_schema is not None
        with patch(
            "hypergolic.sandbox.tool.project_tool.run_in_sandbox", side_effect=fake_run
        ):
            await invoke(tool, tool.input_schema(command="ls"), ctx)

        assert compose.exists()


async def test_lazy_start_broadcasts_sandbox_status():
    from unittest.mock import AsyncMock

    from hypergolic.sandbox.manager.types import ExecResult
    from hypergolic.sandbox.tool.exec import run_in_sandbox

    session = build_session()
    broadcast = AsyncMock()
    ctx = ToolContext(session=session, broadcast=broadcast, tool_id="cmd")
    ok = ExecResult(stdout="hi\n", stderr="", returncode=0)

    with (
        patch("hypergolic.sandbox.tool.exec.start_sandbox", new=AsyncMock()) as start,
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", new=AsyncMock(return_value=ok)),
    ):
        result = await run_in_sandbox(ctx, "/tmp/compose.yaml", "echo hi")

    assert not result.is_error
    start.assert_awaited_once()
    events = [c.args[0] for c in broadcast.await_args_list]
    assert any(e.type == "sandbox_status_change" and e.content == [{"status": "running"}] for e in events)


async def test_running_sandbox_does_not_broadcast_status():
    from unittest.mock import AsyncMock, MagicMock

    from hypergolic.sandbox.manager.types import ExecResult
    from hypergolic.sandbox.tool.exec import run_in_sandbox

    session = build_session()
    broadcast = AsyncMock()
    ctx = ToolContext(session=session, broadcast=broadcast, tool_id="cmd")
    ok = ExecResult(stdout="hi\n", stderr="", returncode=0)
    running = MagicMock(status="running")

    with (
        patch("hypergolic.sandbox.manager.sandbox_rows.get", new=AsyncMock(return_value=running)),
        patch("hypergolic.sandbox.tool.exec.needs_start", new=MagicMock(return_value=False)),
        patch("hypergolic.sandbox.tool.exec.exec_in_sandbox", new=AsyncMock(return_value=ok)),
    ):
        result = await run_in_sandbox(ctx, "/tmp/compose.yaml", "echo hi")

    assert not result.is_error
    assert all(c.args[0].type != "sandbox_status_change" for c in broadcast.await_args_list)
