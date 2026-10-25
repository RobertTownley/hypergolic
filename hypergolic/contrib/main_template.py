"""
Hypergolic harness configuration.

This file is the entry point — it registers and customizes, not implements.
As your harness grows, put tools in tools/, skills in skills/, and
project setup in projects/<id>/tools.py.

Run with: h (shell alias set up by `hypergolic init`)
"""
from hypergolic import App, Project  # noqa: F401

app = App()

# Register the built-in tools, roles, and skills (imported from the package).
app.use_defaults()

# --- Customize the defaults -------------------------------------------------
# Adjust the built-ins instead of forking them. A few examples:
#
# app.modify_role("generalist", remove_tools=["host_cmd"], add_skills=[my_skill])
# app.override_skill("history", prompt_path="~/.hypergolic/prompts/skills/history.md")
# app.override_tool("git", approval=my_approval_policy)
# app.override_role("worker", strip_history_thinking=False)  # replay its thinking
#
# Override or disable the default (generalist) base system prompt:
# app.set_system_prompt(prompt="You are a focused coding assistant.")
# app.set_system_prompt(path="~/.hypergolic/prompts/system.md")
# app.set_system_prompt()  # disable the default base prompt entirely
#
# Or keep the default and append your own cross-project guidance after it:
# app.append_system_prompt(prompt="Prefer uv over pip. Always write tests.")
# app.append_system_prompt(path="~/.hypergolic/prompts/guidance.md")
#
# Append to a built-in role's prompt (e.g. extra review criteria):
# app.append_role_prompt("reviewer", prompt="Flag any missing DB migrations.")
# app.append_role_prompt("reviewer", path="~/.hypergolic/prompts/review.md")

# --- Projects ---------------------------------------------------------------
# Register your projects here. Example:
#
# from projects.my_project.tools import setup_my_project
# setup_my_project(app)

if __name__ == "__main__":
    app()
