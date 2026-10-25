# Conversing with Your Assistant

Hypergolic is a conversation-driven tool. The quality of your results depends largely on how you communicate with the assistant. This guide covers practical techniques for getting the most out of your sessions.

## The Basics

### Be Direct

The assistant works best with clear, specific requests. Instead of vague asks, state what you want:

- ❌ *"Can you help with the tests?"*
- ✅ *"The test suite in `tests/test_api.py` is failing. Run it, diagnose the failures, and fix them."*

### Provide Context

When the assistant doesn't know something, tell it. It can explore your codebase with tools, but a sentence of context saves time:

- *"The `UserService` class in `src/services/user.py` handles all auth logic. I want to add rate limiting to the login endpoint."*
- *"We just upgraded from Django 4.2 to 5.1. Some middleware changed — check the changelog."*

### Watch It Work

Tool calls stream in real time. Each one is expandable so you can see inputs and outputs. Watching the tool calls helps you:

- Verify it's looking at the right files
- Catch misunderstandings early
- Learn what tools are available

### Correct Early

If the assistant is heading in the wrong direction, interrupt it. Corrections are cheaper early.

- *"Don't use raw SQL — we use SQLAlchemy for all queries in this project."*
- *"That's the wrong test runner. We use `pytest`, not `unittest`."*

## Approval Prompts

When the assistant needs to run a shell command or write/edit files, you'll be prompted to approve. **Read the details before approving**, especially for destructive operations like file deletions or git force-pushes.

| Key | Action |
|-----|--------|
| `Y` | Approve |
| `N` | Deny |
| `D` | Deny with a message |
| `C` | Open a harness session to configure approval policy |

Denying with a message (`D`) is powerful — it tells the assistant *why* you said no, so it can adjust its approach.

## Working Styles

Different tasks call for different levels of autonomy.

### Autonomous Mode

For well-defined tasks, let the assistant run:

- *"Add input validation to all API endpoints. Run the tests after each change to make sure nothing breaks."*
- *"Refactor the logging module to use structured logging. Here's the pattern I want: [example]."*

### Collaborative Mode

For exploratory or high-stakes work, ask it to check in:

- *"I want to redesign the caching layer. Let's discuss the approach before you write any code."*
- *"Walk me through what you'd change, then I'll tell you which parts to implement."*

### Review Mode

Use the assistant as a reviewer rather than an implementer:

- *"Review the changes on this branch. Focus on correctness and edge cases."*
- *"Read through `src/auth/` and tell me what security concerns you see."*

## Effective Patterns

### Start with Exploration

When beginning work in an unfamiliar area, ask the assistant to read first:

- *"Read the README and summarize what this project does."*
- *"Look at the test suite and tell me how it's structured before we add new tests."*

### Break Down Large Tasks

Big tasks benefit from explicit decomposition:

- *"Let's migrate to the new API in three steps: first update the client library, then update the endpoints, then update the tests. Start with step one."*

### Use File Attachments

Drag screenshots, diagrams, or error messages into the chat. This is especially useful for:

- UI bugs (screenshot the broken state)
- Error messages (screenshot the terminal)
- Architecture diagrams (explain what you want to change)

### Run Multiple Sessions

Use `⌘/Ctrl + N` to start parallel sessions. Each one runs independently. Use `⌘/Ctrl + J` to jump between them as they need attention. This is effective for:

- Running tests in one session while implementing in another
- Investigating a bug while continuing feature work
- Letting one session handle a mechanical refactor while you focus elsewhere

## When Things Go Wrong

### The Assistant Is Stuck

If it's going in circles, provide concrete direction:

- *"Stop trying to fix the import. The issue is that the module isn't installed. Run `uv add requests`."*

### It Misunderstands the Task

Restate what you want clearly, and tell it what it got wrong:

- *"No — I don't want to change the API. I want to add a new endpoint that does X, leaving the existing ones untouched."*

### It Produces Low-Quality Output

Be specific about what's wrong and what you expect:

- *"This test doesn't actually verify the behavior. Write a test that checks the return value when the input is empty."*
- *"The error handling is too broad. Catch specific exceptions, not bare `except`."*

## Concluding Sessions

When a task is done, press `⌘/Ctrl + Enter` to conclude. Rate the session and leave feedback — these signals help you identify patterns in your work over time.

## Further Reading

- [Getting Started](getting-started.md) — Interface overview and keyboard shortcuts
- [Harness Engineering](harness-engineering.md)
- [Tools](tools.md) — What the assistant can do
- [Advanced Usage](advanced-usage.md#tips-for-effective-prompt-engineering) — Writing prompts for roles, skills, and projects
