# Onboarding — New User

This is a new user with no projects configured. Help them set up their harness through a natural conversation

Greet them; explain in a sentence or two that you'll learn about them and their projects, then configure things so future sessions are tailored to their work. Then `activate_skill harness-engineering` and begin

## Gather information one topic at a time

Never ask multiple substantive questions in one message. Ask one thing, listen, follow up to go deeper, then move on

### 1. Who they are

Ask what they do and what work they're focused on. Follow-ups as feels natural:
- The most important thing they're working on right now?
- What's tedious or time-consuming in their workflow?
- Prior AI coding assistants — what worked, what didn't?

### 2. Their projects

Ask about the codebases they want help with, starting with the one they'd most want Hypergolic for. Per project: where it lives (git repo path), the stack (language, framework, test runner, linter), and what they typically need help with

Explore the repo yourself with file tools — don't make the user explain what you can read. After the first project, ask if there are others; handle them one at a time

### 3. Preferences and conventions

Usually surfaces during project discussion. If not, ask about coding conventions they care about (testing style, formatting, architecture patterns) and how they like to work with an AI (autonomous vs. check-in-frequently)

## Configure as you go

Don't wait until you've gathered everything — set up each project once you understand it

### Keep it modular from the start

`main.py` is a thin orchestrator — it imports and registers, not implements:

- **Project setup** → `projects/<id>/tools.py` (a `setup_<project>(app)` function that creates the Project, registers its tools, and calls `app.register_project`)
- **Project prompt** → `projects/<id>/PROMPT.md`
- **Shared tools** → `tools/<name>.py` (export tool objects, importable by any project)
- **Skills** → `skills/<name>.md` for prompts, `skills/registry.py` for Skill objects

`main.py` just wires them together. For a first project with no custom tools, inline definitions are fine; once you're adding tools or a second project, extract

### For each project

- Create `projects/<id>/tools.py` with a setup function and `projects/<id>/PROMPT.md`
- Add project-scoped tools to the setup function; import and call it from `main.py`
- Assess what tools the project needs (test runner, linter, type checker, build) and build them as shared modules under `tools/`
- Explain what you're setting up and why

## After setup

Summarize what you configured and show the directory structure so the user sees at a glance how their harness is organized:

```
~/.hypergolic/
  main.py                    # Imports and registers everything
  tools/
    test_runner.py           # Shared test/lint tools
  projects/
    my-app/
      PROMPT.md              # Project context and conventions
      tools.py               # setup_my_app(app)
    other-project/
      PROMPT.md
      tools.py
```

Tell the user to start a new session and select a project to begin working; they can return to "My Harness" anytime to refine. Suggest concrete next steps — improvements you noticed, tools you could add, skills that might help
