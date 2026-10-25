from hypergolic.contrib.tools.activate_skill import activate_skill_tool
from hypergolic.contrib.tools.list_skills import list_skills_tool
from hypergolic.contrib.tools.apropos import apropos_tool
from hypergolic.contrib.tools.harness_validate import validate_harness_tool
from hypergolic.contrib.tools.reload_harness import reload_harness_tool
from hypergolic.contrib.tools.restart import restart_tool

#: Git needs no tool anymore: session repos are sandbox-owned, so the image's
#: own git works in /app (see docs/sandbox-lifecycle.md). `apropos` is
#: universal because it is how a session finds the rest of its capability; a
#: role that omitted it would leave the agent with only the one-line index and
#: no way down into the detail.
UNIVERSAL_TOOLS = [apropos_tool, activate_skill_tool, list_skills_tool]

HARNESS_ENGINEER_TOOLS = [
    validate_harness_tool,
    reload_harness_tool,
    restart_tool,
]
