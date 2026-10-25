from typing import Any

from hypergolic.commands.registry import SHELL_COMMAND_ID
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives.approval import ApprovalContext, always
from hypergolic.harness.primitives.bundles import Role
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool
from hypergolic.harness.project import Project
from tests._factories import build_session, build_skill, commands_for
from tests.conftest import make_project, make_session


class Args(InputSchema):
    target: str


async def _tool_run(inp, _ctx):
    return ToolResult.text(f"ran {inp.target}")


def shorthand_tool(tool_id: str = "deploy", **overrides) -> Tool:
    fields: dict[str, Any] = dict(
        id=tool_id,
        name=tool_id.title(),
        description="Ship it.\nSecond paragraph of guidance.",
        input_schema=Args,
        run=_tool_run,
        approval="REQUIRE_APPROVAL",
    )
    fields.update(overrides)
    return Tool(**fields)


def _app_with(*, skills=(), tools=()) -> App:
    app = App()
    app.register_role(Role(id="generalist", name="G", prompt="t"))
    for skill in skills:
        app.register_skill(skill)
    if tools:
        app.register_tools(list(tools))
    app.register_project(Project(id="p-1", name="P", description="d", git_root="/tmp/p"))
    set_app(app)
    return app


def _session():
    make_project("p-1", "P", "/tmp/p")
    sid = make_session(project_id="p-1", sid="s1")
    return build_session(sid=sid, project_id="p-1", project_path="/tmp/p")


def test_a_tools_first_line_is_relevance_and_the_rest_is_guidance():
    command = shorthand_tool()
    assert command.description == "Ship it."
    assert command.guidance == "Second paragraph of guidance."


def test_a_string_approval_becomes_a_total_policy():
    decision = shorthand_tool().approval_policy(ApprovalContext(input=None, session=None))
    assert decision.decision == "REQUIRE_APPROVAL"


def test_the_registry_infers_the_argv_parser_a_declaration_left_out():
    _app_with(tools=[shorthand_tool()])
    command = commands_for(_session())["deploy"]
    assert command.usage.startswith("deploy")
    assert command.parse is not None
    assert command.parse(["prod"]) == Args(target="prod")


def test_a_declared_parser_and_usage_survive_the_registry():
    async def run(_inp, _ctx):
        return ToolResult.text("ok")

    declared = Tool(
        id="probe",
        name="Probe",
        description="Poke it.",
        usage="probe <thing>",
        approval=always("ALLOW"),
        run=run,
    )
    _app_with(skills=[build_skill("probing", prompt="p", tools=[declared])])
    resolved = commands_for(_session())["probe"]
    assert resolved.usage == "probe <thing>"
    assert resolved.origin == "skill:probing"
    assert resolved.run is declared.run


def test_skill_tools_are_reachable_without_activation():
    _app_with(skills=[build_skill("deployment", prompt="how to ship", tools=[shorthand_tool()])])
    commands = commands_for(_session())
    assert "deploy" in commands
    assert commands["deploy"].origin == "skill:deployment"


def test_a_prompt_only_skill_becomes_documentation_with_nothing_to_invoke():
    _app_with(skills=[build_skill("acme-database", prompt="guidance body")])
    commands = commands_for(_session())
    assert not commands["acme-database"].invocable
    assert "guidance body" in commands["acme-database"].guidance


def test_a_skill_with_tools_still_publishes_its_guidance():
    _app_with(skills=[build_skill("deployment", prompt="how to ship", tools=[shorthand_tool()])])
    commands = commands_for(_session())
    assert "how to ship" in commands["deployment"].guidance
    assert not commands["deployment"].invocable


def test_guidance_rides_the_tool_a_skill_names_after_itself():
    tool = shorthand_tool().model_copy(update={"id": "design", "guidance": ""})
    _app_with(skills=[build_skill("design", prompt="read the design first", tools=[tool])])
    command = commands_for(_session())["design"]
    assert command.invocable
    assert "read the design first" in command.guidance


def test_a_skill_annotates_a_co_named_command_it_does_not_own():
    tool = shorthand_tool().model_copy(update={"id": "git", "guidance": "one subcommand per call"})
    _app_with(
        tools=[tool],
        skills=[build_skill("git", prompt="commit as you go", tools=[shorthand_tool("merge")])],
    )
    commands = commands_for(_session())
    assert commands["git"].invocable
    assert "one subcommand per call" in commands["git"].guidance
    assert "commit as you go" in commands["git"].guidance
    assert "merge" in commands


def test_a_co_named_tools_own_guidance_survives_the_skill_prompt():
    tool = shorthand_tool().model_copy(update={"id": "git", "guidance": "one subcommand per call"})
    _app_with(skills=[build_skill("git", prompt="commit as you go", tools=[tool])])
    guidance = commands_for(_session())["git"].guidance
    assert "one subcommand per call" in guidance
    assert "commit as you go" in guidance


def test_the_shell_is_the_wire_tool_and_never_a_command():
    _app_with()
    assert SHELL_COMMAND_ID not in commands_for(_session())
