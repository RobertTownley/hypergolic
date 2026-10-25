from __future__ import annotations

from pydantic import Field

from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext


class ActivateSkillInput(InputSchema):
    name: str = Field(description="Skill id, as shown by `apropos`.")


def _key(name: str) -> str:
    return name.strip().lower().replace("_", "-")


async def run_activate_skill(inp: ActivateSkillInput, ctx: ToolContext) -> ToolResult:
    from hypergolic.commands.registry import resolvable_skills, skill_activation_text
    from hypergolic.skills import activation_rows

    pairs = resolvable_skills(ctx.session)
    key = _key(inp.name)
    if key == _key("list_skills"):
        from hypergolic.contrib.tools.list_skills import ListSkillsInput, run_list_skills

        return await run_list_skills(ListSkillsInput(), ctx)
    skills = {skill.id: skill for skill, _ in pairs}
    skill = skills.get(inp.name) or {_key(s): v for s, v in skills.items()}.get(key)
    if skill is None:
        return ToolResult.text(
            f"No skill '{inp.name}'. Available: {', '.join(sorted(skills))}",
            is_error=True,
        )
    await activation_rows.record(ctx.session.id, skill.id)
    return ToolResult.text(skill_activation_text(skill))


activate_skill_tool = Tool(
    id="activate_skill",
    name="Activate Skill",
    description="Load a skill's specialized context, tools, and subskills",
    tags=["skill", "activate", "load", "context", "guidance", "specialized",
        "domain-knowledge", "how-do-i"],
    input_schema=ActivateSkillInput,
    run=run_activate_skill,
    approval=always("ALLOW"),
)
