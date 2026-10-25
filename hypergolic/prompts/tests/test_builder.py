from unittest.mock import patch

import pytest

from hypergolic.prompts.builder import (
    DEFAULT_SYSTEM_PROMPT,
    PromptBlock,
    _session_context_block,
    _build_activated_skills_block,
    _build_workflow_prompt_blocks,
    build_prompt_blocks,
    live_prompt_blocks,
    frozen_prompt_blocks,
)
from hypergolic.prompts.blocks import to_text_blocks
from hypergolic.prompts.store import load_prompt_blocks, save_prompt_blocks
from hypergolic.schemas import Session
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives.bundles import Role, Workflow, WorkflowState
from hypergolic.harness.project import Project
from tests._factories import build_session
from tests.conftest import make_session
from hypergolic.sandbox.model.containers import Container, HostMount
from hypergolic.sandbox.model.sandbox import ProjectSandbox
from hypergolic.sandbox.model.egress import Egress
from hypergolic.sandbox.model.containers import Port


def _session(
    sid: str = "s-1",
    project_id: str = "p-1",
    role: str = "generalist",
    dispatch_prompt: str | None = None,
) -> Session:
    return build_session(
        sid=sid,
        project_id=project_id,
        project_path="/tmp/base",
        role=role,
        dispatch_prompt=dispatch_prompt,
        worktree_path="/tmp/wt/main-s-1",
        worktree_branch="main-s-1",
        base_branch="main",
    )


def _app(*, roles: list[Role] | None = None, project: Project | None = None) -> App:
    app = App()
    if roles is None:
        roles = [Role(id="generalist", name="Generalist", prompt="You are Hypergolic.")]
    for role in roles:
        app.register_role(role)
    app.register_project(
        project or Project(id="p-1", name="P", description="d", git_root="/tmp/p")
    )
    set_app(app)
    return app


async def _blocks(session: Session | None = None) -> list[PromptBlock]:
    with patch("hypergolic.prompts.builder.get_session_workflow", return_value=None):
        return await build_prompt_blocks(session or _session())


def _build_session_context(session: Session) -> str:
    block = _session_context_block(session)
    return block.text if block else ""


def _sources(blocks: list[PromptBlock]) -> list[str]:
    return [b.source for b in blocks]


def _base(blocks: list[PromptBlock]) -> PromptBlock:
    return next(b for b in blocks if b.source == "Base prompt")


def test_prompt_block_to_text_block():
    block = PromptBlock(source="test", text="hello world")
    assert block.to_text_block() == {"type": "text", "text": "hello world"}


async def test_base_prompt_overrides(tmp_path):
    _app()
    assert "Base prompt" in _sources(await _blocks())

    _app(roles=[])
    assert _base(await _blocks()).text == DEFAULT_SYSTEM_PROMPT

    _app().set_system_prompt(prompt="Custom base prompt.")
    assert _base(await _blocks()).text == "Custom base prompt."

    prompt_file = tmp_path / "sys.md"
    prompt_file.write_text("From a file.")
    _app().set_system_prompt(path=str(prompt_file))
    assert _base(await _blocks()).text == "From a file."

    _app().set_system_prompt()
    assert "Base prompt" not in _sources(await _blocks())


async def test_append_system_prompt(tmp_path):
    prompt_file = tmp_path / "guidance.md"
    prompt_file.write_text("From a file.")
    app = _app()
    app.append_system_prompt(prompt="First guidance.")
    app.append_system_prompt(path=str(prompt_file))
    blocks = await _blocks()
    sources = _sources(blocks)
    assert sources.index("Base prompt") < sources.index("User guidance")
    assert [b.text for b in blocks if b.source == "User guidance"] == ["First guidance.", "From a file."]

    app.set_system_prompt()
    blocks = await _blocks()
    assert "Base prompt" not in _sources(blocks)
    assert len([b for b in blocks if b.source == "User guidance"]) == 2

    with pytest.raises(ValueError):
        app.append_system_prompt()
    with pytest.raises(ValueError):
        app.append_system_prompt(path="x", prompt="y")


@pytest.mark.parametrize(
    "worker_role, session_role, expect_role_block",
    [
        (Role(id="worker", name="Worker", prompt="Worker prompt"), "worker", True),
        (Role(id="worker", name="Worker"), "worker", False),
        (None, "nonexistent-role", False),
    ],
)
async def test_build_prompt_blocks_role_block(worker_role, session_role, expect_role_block):
    roles = [Role(id="generalist", name="Generalist", prompt="Base")]
    if worker_role:
        roles.append(worker_role)
    _app(roles=roles)

    blocks = await _blocks(_session(role=session_role))
    has_role_block = any("Role prompt" in s for s in _sources(blocks))
    assert has_role_block is expect_role_block


@pytest.mark.parametrize("project_prompt", ["Project-level prompt", None])
async def test_build_prompt_blocks_project_prompt(project_prompt):
    _app(
        roles=[Role(id="generalist", name="Generalist", prompt="Base")],
        project=Project(id="p-1", name="P", description="d", git_root="/tmp", prompt=project_prompt),
    )
    sources = _sources(await _blocks())
    assert ("User-project guidance" in sources) is (project_prompt is not None)


async def test_build_prompt_blocks_dispatch_prompt():
    _app()
    blocks = await _blocks(_session(dispatch_prompt="You are a worker"))
    assert "Dispatch context" in _sources(blocks)
    assert "You are a worker" in next(b for b in blocks if b.source == "Dispatch context").text

    assert "Dispatch context" not in _sources(await _blocks())


def _workflow_blocks(wf, state_id: str = "st-1") -> list[PromptBlock]:
    lookup = ("wf-1", state_id) if wf else None
    with (
        patch("hypergolic.prompts.builder.get_session_workflow", return_value=lookup),
        patch("hypergolic.prompts.builder.get_workflow", return_value=wf),
    ):
        return _build_workflow_prompt_blocks(_session())


def test_build_workflow_prompt_blocks_no_active_workflow():
    _app()
    assert _workflow_blocks(None) == []


def test_activated_skills_block_absent_until_something_is_activated():
    _app()
    make_session(project_id="p-1", sid="s-1")
    assert _build_activated_skills_block(_session()) is None


async def test_activated_skills_block_names_skills_and_points_at_reload():
    from hypergolic.skills import activation_rows

    _app()
    make_session(project_id="p-1", sid="s-1")
    await activation_rows.record("s-1", "git")
    await activation_rows.record("s-1", "knowledge-base")

    live = await live_prompt_blocks(_session())
    block = next(b for b in live if b.source == "Activated skills")
    assert "git, knowledge-base" in block.text
    assert "activate_skill <id>" in block.text
    assert "Activated skills" not in _sources(await frozen_prompt_blocks(_session(), persist=False))


def test_build_workflow_prompt_blocks_workflow_not_found():
    _app()
    with (
        patch("hypergolic.prompts.builder.get_session_workflow", return_value=("wf-x", "st-1")),
        patch("hypergolic.prompts.builder.get_workflow", return_value=None),
    ):
        blocks = _build_workflow_prompt_blocks(_session())
    assert blocks == []


@pytest.mark.parametrize("wf_prompt", ["Workflow prompt content", None])
def test_build_workflow_prompt_blocks_workflow_and_state_prompts(wf_prompt):
    _app()
    wf = Workflow(
        id="wf-1",
        name="Test WF",
        description="d",
        initial_state="st-1",
        prompt=wf_prompt,
        states=[WorkflowState(id="st-1", name="State One", prompt="state prompt")],
    )
    sources = _sources(_workflow_blocks(wf))
    assert any("Workflow: Test WF" in s for s in sources) is (wf_prompt is not None)
    assert any("Workflow State: State One" in s for s in sources)


def test_build_workflow_prompt_blocks_state_not_found_in_workflow():
    _app()
    wf = Workflow(
        id="wf-1",
        name="WF",
        description="d",
        initial_state="st-1",
        states=[WorkflowState(id="st-1", name="S", prompt="p")],
    )
    assert isinstance(_workflow_blocks(wf, state_id="st-missing"), list)


async def test_prompt_blocks_render_as_text_blocks():
    _app()
    with patch("hypergolic.prompts.builder.get_session_workflow", return_value=None):
        result = to_text_blocks(await build_prompt_blocks(_session()))
    assert isinstance(result, list)
    assert all(b["type"] == "text" for b in result)
    assert len(result) >= 1


def _sandbox_app(sandbox, *, pid: str = "acme") -> None:
    project = Project(id=pid, name="Acme App", description="d", git_root=f"/tmp/{pid}")
    project.configure_sandbox(sandbox)
    _app(project=project)


def test_sandbox_context_multi_container():
    _sandbox_app(ProjectSandbox(
        id="acme-sandbox",
        containers=[
            Container(id="api", image="python:3.12", expose=[Port(container=8000, name="api")]),
            Container(id="frontend", image="node:22"),
        ],
        egress=Egress.Allow(["https://pypi.org"]),
    ))
    session = build_session(sid="s-sb", project_id="acme", project_path="/tmp/acme")

    ctx = _build_session_context(session)

    assert "Sandbox acme-sandbox: containers api, frontend" in ctx
    assert "egress limited to pypi.org" in ctx
    assert "/shared" not in ctx
    assert "Worktree at /app is one shared tree across containers" in ctx


def test_sandbox_context_single_container():
    _sandbox_app(ProjectSandbox(
        id="acme-sandbox", containers=[Container(id="dev", image="python:3.12")]
    ))
    session = build_session(sid="s-one", project_id="acme", project_path="/tmp/acme")

    ctx = _build_session_context(session)

    assert "Sandbox acme-sandbox: container dev" in ctx
    assert "/app" not in ctx
    assert "all containers" not in ctx


def test_sandbox_context_renders_host_mounts():
    _sandbox_app(ProjectSandbox(
        id="acme-sandbox",
        containers=[
            Container(
                id="api",
                image="python:3.12",
                host_mounts=[HostMount(source="~/acme", target="/acme")],
            ),
            Container(
                id="frontend",
                image="node:22",
                host_mounts=[HostMount(source="/opt/data", target="/data", read_only=False)],
            ),
        ],
    ))
    session = build_session(sid="s-hm", project_id="acme", project_path="/tmp/acme")

    ctx = _build_session_context(session)

    assert "host ~/acme ro /acme (api)" in ctx
    assert "host /opt/data rw /data (frontend)" in ctx


def test_sandbox_context_default_when_unconfigured():
    _app()
    session = build_session(sid="s-default", project_path="/tmp/p")
    ctx = _build_session_context(session)
    assert "Sandbox default:" in ctx
    assert "egress deny all" in ctx


def test_sandbox_context_absent_when_project_opts_out():
    _sandbox_app(None, pid="p-1")
    session = build_session(sid="s-nosb", project_path="/tmp/x")
    ctx = _build_session_context(session)
    assert "Sandbox" not in ctx


def _project(prompt: str) -> Project:
    return Project(id="p-1", name="P", description="d", git_root="/tmp/p", prompt=prompt)


async def test_frozen_prompt_blocks_freeze_on_first_turn():
    _app(project=_project("v1"))
    sid = make_session(project_id="p-1")
    session = _session(sid=sid)

    frozen = await frozen_prompt_blocks(session, persist=True)
    assert load_prompt_blocks(sid) == frozen
    assert "v1" in _text(frozen, "User-project guidance")

    _app(project=_project("v2"))
    assert await frozen_prompt_blocks(session, persist=True) == frozen
    unfrozen = await frozen_prompt_blocks(_session(sid=make_session()), persist=False)
    assert "v2" in _text(unfrozen, "User-project guidance")


async def test_build_prompt_blocks_serves_stored_blocks_and_never_freezes():
    _app(project=_project("v1"))
    sid = make_session(project_id="p-1")
    save_prompt_blocks(sid, [PromptBlock(source="Base prompt", text="stored")])

    blocks = await _blocks(_session(sid=sid))
    assert _text(blocks, "Base prompt") == "stored"
    assert "Live context" not in _sources(blocks)

    fresh = make_session(project_id="p-1")
    await _blocks(_session(sid=fresh))
    assert load_prompt_blocks(fresh) is None


def _text(blocks: list[PromptBlock], source: str) -> str:
    return next(b.text for b in blocks if b.source == source)
