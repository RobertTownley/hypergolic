"""`list_skills` — enumerate every skill this session can activate.

`apropos` finds skills by intent; this is the browse path for an agent asking
"what specialized context exists at all?" — one line per skill, ready to feed
to `activate_skill`.
"""

from __future__ import annotations

from hypergolic.commands.registry import resolvable_skills
from hypergolic.harness.primitives import (
    InputSchema,
    Tool,
    ToolContext,
    ToolResult,
    always,
)


class ListSkillsInput(InputSchema):
    pass


async def run_list_skills(inp: ListSkillsInput, ctx: ToolContext) -> ToolResult:
    skills = resolvable_skills(ctx.session)
    if not skills:
        return ToolResult.text("No skills available in this session.")
    lines = []
    for skill, origin in sorted(skills, key=lambda pair: pair[0].id):
        via = f"  (subskill of {origin[6:]})" if origin.startswith("skill:") else ""
        lines.append(f"- {skill.id} \u2014 {skill.description or skill.name}{via}")
    body = "\n".join(lines)
    return ToolResult.text(f"{body}\n\n`activate_skill <id>` to load one.")


list_skills_tool = Tool(
    id="list_skills",
    name="List Skills",
    description="List every skill this session can activate",
    tags=["skill", "list", "discover", "available", "catalog", "browse"],
    input_schema=ListSkillsInput,
    run=run_list_skills,
    approval=always("ALLOW"),
)
