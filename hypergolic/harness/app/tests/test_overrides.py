"""Tests for App.use_defaults() and the override/modify mutators."""
import pytest

from hypergolic import App, Tool
from hypergolic.harness.primitives.bundles import Role, Skill, resolve_prompt
from tests._factories import build_skill
from hypergolic.harness.primitives.approval import ApprovalContext, TotalPolicy
from hypergolic.contrib.roles.registry import generalist_role


async def _noop(inp, ctx):  # pragma: no cover - never executed
    return None


def _app() -> App:
    app = App()
    app.use_defaults()
    return app


def _role(app: App, role_id: str) -> Role:
    role = app.get_role(role_id)
    assert role is not None
    return role


def _skill(app: App, skill_id: str) -> Skill:
    skill = app.get_skill(skill_id)
    assert skill is not None
    return skill


def test_use_defaults_registers_builtins():
    app = _app()
    assert app.get_role("generalist") is not None
    assert app.get_skill("history") is not None
    assert {r.id for r in app.roles} >= {"generalist", "researcher", "reviewer"}


def test_use_defaults_is_isolated_per_app():
    """Mutating one App must not leak into another or the module-level contrib."""

    a, b = _app(), _app()
    a.modify_role("generalist", remove_tools=["host_cmd"])

    assert "host_cmd" not in {t.id for t in _role(a, "generalist").tools}
    assert "host_cmd" in {t.id for t in _role(b, "generalist").tools}
    assert "host_cmd" in {t.id for t in generalist_role.tools}  # shared object untouched


def test_modify_role_add_and_remove_tools():
    app = _app()
    extra = Tool(id="extra", name="Extra", description="", run=_noop)
    app.modify_role("generalist", add_tools=[extra], remove_tools=["host_cmd"])
    ids = {t.id for t in _role(app, "generalist").tools}
    assert "extra" in ids and "host_cmd" not in ids


def test_modify_role_skills():
    app = _app()
    app.modify_role("generalist", add_skills=[build_skill("custom")], remove_skills=["history"])
    ids = {s.id for s in _role(app, "generalist").skills}
    assert "custom" in ids and "history" not in ids


def test_modify_role_add_is_idempotent_by_id():
    app = _app()
    extra = Tool(id="extra", name="Extra", description="", run=_noop)
    app.modify_role("generalist", add_tools=[extra])
    app.modify_role("generalist", add_tools=[extra])
    ids = [t.id for t in _role(app, "generalist").tools]
    assert ids.count("extra") == 1


def test_override_skill_applies_everywhere():
    app = _app()
    app.override_skill("history", prompt="custom db prompt")
    assert _skill(app, "history").prompt == "custom db prompt"
    role_skill = next(s for s in _role(app, "generalist").skills if s.id == "history")
    assert role_skill.prompt == "custom db prompt"
    assert role_skill.prompt_path is None  # exclusivity: other prompt sources cleared


def test_override_tool_applies_everywhere():
    app = _app()
    app.override_tool("host_cmd", timeout=99)
    role_cmd = next(t for t in _role(app, "generalist").tools if t.id == "host_cmd")
    assert role_cmd.timeout == 99


def test_remove_tool_removes_everywhere():
    app = _app()
    app.remove_tool("history")
    assert "history" not in {t.id for t in _role(app, "generalist").tools}
    db_skill = _skill(app, "history")
    assert "history" not in {t.id for t in db_skill.tools}


def test_remove_skill_removes_everywhere():
    app = _app()
    app.remove_skill("history")
    assert app.get_skill("history") is None
    for role in app.roles:
        assert "history" not in {s.id for s in role.skills}


def test_remove_skill_scoped_to_role():
    app = _app()
    app.remove_skill("history", role_id="generalist")
    assert "history" not in {s.id for s in _role(app, "generalist").skills}
    assert app.get_skill("history") is not None


def test_remove_skill_scoped_missing_on_role_raises():
    app = _app()
    app.remove_skill("history", role_id="generalist")
    with pytest.raises(KeyError):
        app.remove_skill("history", role_id="generalist")


def test_override_role_prompt():
    app = _app()
    app.override_role("reviewer", prompt="be terse")
    assert _role(app, "reviewer").prompt == "be terse"


def test_append_role_prompt_keeps_original():
    app = _app()
    original = resolve_prompt(_role(app, "reviewer"), app)
    assert original
    app.append_role_prompt("reviewer", prompt="Check for SQL injection.")
    combined = resolve_prompt(_role(app, "reviewer"), app)
    assert combined == f"{original.rstrip()}\n\nCheck for SQL injection."


def test_append_role_prompt_stacks():
    app = _app()
    app.append_role_prompt("reviewer", prompt="First.")
    app.append_role_prompt("reviewer", prompt="Second.")
    combined = resolve_prompt(_role(app, "reviewer"), app)
    assert combined and combined.endswith("First.\n\nSecond.")


def test_append_role_prompt_path(tmp_path):
    app = _app()
    f = tmp_path / "review.md"
    f.write_text("From a file.")
    app.append_role_prompt("reviewer", path=str(f))
    combined = resolve_prompt(_role(app, "reviewer"), app)
    assert combined and combined.endswith("From a file.")


def test_append_role_prompt_after_override():
    app = _app()
    app.override_role("reviewer", prompt="be terse")
    app.append_role_prompt("reviewer", prompt="Extra.")
    assert resolve_prompt(_role(app, "reviewer"), app) == "be terse\n\nExtra."


def test_append_role_prompt_requires_exactly_one_arg():
    app = _app()
    with pytest.raises(ValueError):
        app.append_role_prompt("reviewer")
    with pytest.raises(ValueError):
        app.append_role_prompt("reviewer", path="x", prompt="y")


@pytest.mark.parametrize("call", [
    lambda app: app.override_skill("nope", prompt="x"),
    lambda app: app.override_tool("nope", timeout=1),
    lambda app: app.override_role("nope", prompt="x"),
    lambda app: app.remove_tool("nope"),
    lambda app: app.remove_skill("nope"),
    lambda app: app.remove_skill("history", role_id="nope"),
    lambda app: app.modify_role("nope", add_tools=[]),
    lambda app: app.append_role_prompt("nope", prompt="x"),
])
def test_unknown_id_raises(call):
    with pytest.raises(KeyError):
        call(_app())


def test_default_prompt_resolves_without_copied_contrib():
    """A default skill's prompt resolves from the package even with no ~/.hypergolic copy."""
    app = _app()
    content = resolve_prompt(app.get_role("generalist"), app)
    assert isinstance(content, str) and content


def test_set_system_prompt_default_is_unset():
    app = _app()
    assert app.resolve_system_prompt("DEFAULT") == "DEFAULT"


def test_set_system_prompt_text():
    app = _app()
    app.set_system_prompt(prompt="Custom.")
    assert app.resolve_system_prompt("DEFAULT") == "Custom."


def test_set_system_prompt_path(tmp_path):
    f = tmp_path / "sys.md"
    f.write_text("From file.")
    app = _app()
    app.set_system_prompt(path=str(f))
    assert app.resolve_system_prompt("DEFAULT") == "From file."


def test_set_system_prompt_disable():
    app = _app()
    app.set_system_prompt()
    assert app.resolve_system_prompt("DEFAULT") is None


def test_set_system_prompt_empty_string_is_literal():
    app = _app()
    app.set_system_prompt(prompt="")
    assert app.resolve_system_prompt("DEFAULT") == ""


def test_set_system_prompt_both_args_raises():
    app = _app()
    with pytest.raises(ValueError):
        app.set_system_prompt(path="x", prompt="y")


def test_set_system_prompt_missing_path_raises():
    app = _app()
    app.set_system_prompt(path="/nonexistent/sys.md")
    with pytest.raises(FileNotFoundError):
        app.resolve_system_prompt("DEFAULT")


def test_override_tool_string_approval_reads_back_as_a_policy():
    """`model_copy(update=...)` skips validation, so the shorthand arrives raw."""

    app = _app()
    app.override_tool("host_cmd", approval="DENY")

    tool = next(t for t in _role(app, "generalist").tools if t.id == "host_cmd")
    assert isinstance(tool.approval_policy, TotalPolicy)
    decision = tool.approval_policy(ApprovalContext(input=None, session=None))
    assert decision.decision == "DENY"
