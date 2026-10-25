import pytest

from hypergolic.contrib.tools.activate_skill import ActivateSkillInput, run_activate_skill
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives.bundles import Skill
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.harness.project import Project
from hypergolic.skills import activation_rows
from tests._factories import build_session
from tests.conftest import make_session


async def _noop_broadcast(event) -> None:  # pragma: no cover
    pass


@pytest.fixture
def ctx():
    child = Skill(id="css", name="CSS", description="Deep CSS conventions", prompt="css prompt")
    tool = Tool(id="lint_styles", name="Lint Styles", description="Lint the stylesheets")
    parent = Skill(
        id="frontend",
        name="Frontend",
        description="Frontend conventions",
        prompt="frontend prompt",
        tools=[tool],
        skills=[child],
    )
    app = App()
    app.register_skills([parent])
    app.register_project(Project(id="p1", name="P1", description="d", git_root="/tmp/t"))
    set_app(app)
    make_session(project_id="p1", sid="s1")
    session = build_session("s1", project_id="p1", project_path="/tmp/t")
    return ToolContext(session=session, broadcast=_noop_broadcast, tool_id="activate_skill")


async def test_activation_names_tools_and_subskills(ctx):
    result = await run_activate_skill(ActivateSkillInput(name="frontend"), ctx)
    text = result.content[0]["text"]
    assert "frontend prompt" in text
    assert "lint_styles" in text
    assert "css — Deep CSS conventions" in text
    assert "activate_skill" in text


async def test_subskill_is_directly_activatable(ctx):
    result = await run_activate_skill(ActivateSkillInput(name="css"), ctx)
    assert "css prompt" in result.content[0]["text"]


async def test_unknown_skill_lists_available(ctx):
    result = await run_activate_skill(ActivateSkillInput(name="nope"), ctx)
    assert result.is_error
    text = result.content[0]["text"]
    assert "frontend" in text and "css" in text
    assert activation_rows.skill_ids("s1") == []


async def test_activation_is_recorded_once_per_skill_under_its_canonical_id(ctx):
    await run_activate_skill(ActivateSkillInput(name="Frontend"), ctx)
    await run_activate_skill(ActivateSkillInput(name="css"), ctx)
    await run_activate_skill(ActivateSkillInput(name="frontend"), ctx)
    assert activation_rows.skill_ids("s1") == ["frontend", "css"]


async def test_a_name_in_other_case_resolves(ctx):
    result = await run_activate_skill(ActivateSkillInput(name="Frontend"), ctx)
    assert "frontend prompt" in result.content[0]["text"]


async def test_list_skills_as_an_argument_lists_the_skills(ctx):
    result = await run_activate_skill(ActivateSkillInput(name="list_skills"), ctx)
    assert not result.is_error
    text = result.content[0]["text"]
    assert "- css \u2014 Deep CSS conventions" in text
