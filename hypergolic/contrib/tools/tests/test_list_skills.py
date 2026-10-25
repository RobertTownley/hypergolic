"""`list_skills`: flat catalog of everything activatable, with subskill provenance."""

import pytest

from hypergolic.contrib.tools.list_skills import ListSkillsInput, run_list_skills
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import set_app
from hypergolic.harness.primitives import Skill, ToolContext
from hypergolic.harness.project import Project
from tests._factories import build_session


async def _noop_broadcast(event) -> None:  # pragma: no cover
    pass


def _ctx(skills):
    app = App()
    app.register_skills(skills)
    app.register_project(Project(id="p1", name="P1", description="d", git_root="/tmp/t"))
    set_app(app)
    session = build_session("s1", project_id="p1", project_path="/tmp/t")
    return ToolContext(session=session, broadcast=_noop_broadcast, tool_id="list_skills")


@pytest.fixture
def ctx():
    child = Skill(id="css", name="CSS", description="Deep CSS conventions", prompt="css prompt")
    parent = Skill(
        id="frontend",
        name="Frontend",
        description="Frontend conventions",
        prompt="frontend prompt",
        skills=[child],
    )
    return _ctx([parent])


async def test_lists_skills_and_subskills(ctx):
    result = await run_list_skills(ListSkillsInput(), ctx)
    text = result.content[0]["text"]
    assert "- css — Deep CSS conventions  (subskill of frontend)" in text
    assert "- frontend — Frontend conventions" in text
    assert "activate_skill" in text  # tells the agent the next step


async def test_empty_catalog():
    result = await run_list_skills(ListSkillsInput(), _ctx([]))
    assert "No skills available" in result.content[0]["text"]
