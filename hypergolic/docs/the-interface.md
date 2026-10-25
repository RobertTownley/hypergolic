# The Interface

Hypergolic comes with a powerful UI that serves as the primary mode of interacting with your agent. Some parts will be familiar to those coming from coding agents, others more novel.

## Session Navigation
All Hypergolic work takes place within sessions. To start a new session, use `cmd + n` and provide the desired parameters of your new session.

To conclude a session, use `cmd + enter`. This will bring up a modal with some options for session conclusion, such as whether you want its work preserved, how you would rate the session (for analytics), and whether you want to initialize a background `recap` session to evaluate the session for proposed harness improvements.

## The Messages Interface
Most of the time, the right side of the screen will be a message ledger of the conversation between you and the agent. 

## File Attachments

Drag files or images into the chat input. The assistant can read images (screenshots, diagrams, error messages) and use them as context.

## Sessions

Conversations are persistent. Each session has its own context and history. Previous sessions are listed in the right sidebar and can be resumed.

### Creating Sessions

Use `⌘/Ctrl + N` to start a fresh session. Each session is tied to the current project and runs independently — you can have multiple sessions active at the same time.

### Jumping Between Sessions (`⌘/Ctrl + J`)

When you're running multiple sessions in parallel, `⌘/Ctrl + J` jumps to the session that most needs your attention. Sessions are prioritized by urgency:

1. **Awaiting approval** — a tool needs your yes/no to proceed
2. **Idle / Interrupted** — waiting for your input
3. **Error** — something went wrong and needs attention
4. **Running** (thinking, streaming, tool use) — working fine, doesn't need you yet
5. **Concluded** — done

Within each tier, the most recently updated session wins. This lets you kick off work in several sessions, then use `⌘/Ctrl + J` to cycle through them as they surface questions or finish.

### Concluding Sessions (`⌘/Ctrl + Enter`)

When a task is complete, press `⌘/Ctrl + Enter` to conclude the session. A modal appears where you can:

- **Rate** the session (1–5)
- **Leave feedback** — optional notes on what went well or poorly

After you submit, the session is marked as concluded and auto-navigates you to the next active session so you can keep moving through parallel work.

The assistant can also conclude sessions on its own using the `conclude` tool when it finishes a dispatched task.

### Session Lifecycle

| Status | Meaning |
|--------|--------|
| **Idle** | Waiting for user input |
| **Thinking / Streaming** | Assistant is generating a response |
| **Tool Use** | Assistant is executing a tool |
| **Awaiting Approval** | A tool needs your approval to proceed |
| **Error** | Something went wrong |
| **Concluded** | Session is finished |
| **Interrupted** | Session was cancelled mid-turn |

## Next Steps

- [Conversing with Your Assistant](conversing.md) — Practical techniques for effective sessions
- [Harness Engineering](harness-engineering.md)
- [Configuration](configuration.md) — Set up your harness, prompts, and projects
- [Tools](tools.md) — Understand what the assistant can do
- [Advanced Usage](advanced-usage.md) — Custom tools, MCP servers, skills, and roles
