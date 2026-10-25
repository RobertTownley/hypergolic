# Hypergolic: Getting Started

These steps will walk you through installing Hypergolic, setting up your harness, and basics of operation of your harness

## Installation

Requirements: macOS, Python 3.14+, [uv](https://docs.astral.sh/uv/), Docker (or [OrbStack](https://orbstack.dev/)), and an Anthropic API key.

```bash
export HYPERGOLIC_API_KEY="your-api-key"
export HYPERGOLIC_BASE_URL="https://api.anthropic.com"

uv tool install hypergolic

hypergolic init
```

Then restart your shell, and use the `h` alias in a terminal to start your first session.

## Your First Conversation

By default, Hypergolic starts with a single project: the harness itself. This is installed to your home directory at `~/.hypergolic/*` and will be the first git repo you work on.

Say "Hello" to the agent, and the agent will walk you through a series of questions around what you want to use the harness for. It will then cross-reference its source code and internal skills to advise how it should be configured. Periodically, it may ask to run a command on your host computer to explore. As your harness matures, the need for the agent to request permission to run arbitrary bash commands decreases significantly, so you never need to go into full "Approval" mode or suffer from approval fatigue.

`Tip`: If you find yourself being asked for approval frequently, ask the agent to offer ideas for how you can safely parameterize common operations. For example, read-only operations, or query executions that have passed through a query plan gate.

Be detailed in describing to the agent details about how you want it to operate. Ideas for good things to offer up:

- What git repos do you plan to work on?
- Do you have any existing resources for agentic configuration (eg org-wide Claude.md files, or Confluent pages on coding best practices)?
- What's your level of comfort with coding more broadly, and with agentic development specifically?
- How involved do you want to be in writing code? Are you more of a vibe coder, or do you prefer to collaborate on code as well as architecture?
- How critical and sensitive is your work by nature? For example, can the agent push directly to main on a personal project or do you want a specific workflow for layers of agentic code review before anything hits your local branch?
- What conventions do you prefer for branch names, for if/how the agent should interact with external systems on your behalf, and what guardrails do you want to agent to honor?

However, don't worry too much about getting it right the first time. Subsequent sessions can configure the harness as well as this first one.

Once the agent has had a chance to configure itself, you'll see it request approval to merge its proposed harness configurations. Review this extensively. Offer comments and feedback for parts you disagree with, or tooling you'd like to see expanded further. Pay particular attention to prompts it writes: LLMs don't yet write prose as effectively as humans, and accurate communication goes a long way towards better outcomes.

For security purposes, harness configuration changes require a human-approved restart to take effect. Once a new configuration has been merged, you can ask the agent to restart the app for you, or you can close out of the app at any time and restart with `h`. This will execute the latest version of `~/.hypergolic/main.py` on your local machine, including configuration of the projects you want to work on.

## Your Next Conversations

All Hypergolic interactions require a session. You can start new sessions with `cmd + N` and conclude sessions with `cmd + enter`. When you start the session, you'll choose which project to work on, and what model tier you want to use (lower tier models are faster and more affordable, higher tiers are smarter and more capable). You'll also choose a `role` for the session. Until you've configured other roles, the built-in `generalist` role is sufficient. I personally almost never use roles other than `generalist`. You'll also select the git branch that the agentic session's code should be based off of.

In this new session, the agent will have access to a copy of your app code within its own sandbox. As you work with the agent to make changes, you'll see the source code of your project change on the left side of the screen. This represents a live diff view of the changes between the base branch and the agent's git repo. As it explores the project at your request, you'll see summaries of what the agent is doing, but you can drill down into the specifics as needed. This can be helpful for uncovering agents repeatedly discovering the same thing slowly or not at all (signs that system prompt or skill hierarchy changes might be worthwhile).

As configured, the agent may periodically request to run potentially-harmful (e.g. shell commands, system file writes, external write operations, etc). When this happens, you'll see an approval box appear detailing the parameters of the requested operation. You can approve or deny, and provide explanatory comments for either result that the agent will see.

When done collaborating with the agent on a feature, it will put forward a `git push` command in its sandbox. This moves its authored code through your configured approval gates (whether human or agentic). This is how agents get code out of their sandbox and safely onto your host machine.

From there, my preferred personal workflow is to have the agent author itself a `github` tool which it can execute (with my approval) to create draft PRs in github. I then review that draft PR as a final human check before merging or putting it up for review by collaborators. However, you can choose to instruct the agent towards whatever workflow makes the most sense for you and your various projects.

## Next Steps

Once you've made an acceptable pass at your project configuration, you should be able to ask the agent questions about your projects. However, it's unlikely that the initial configuration session left your harness in a satisfactory place. To get greater outcomes, you'll want to think comprehensively about the building blocks of your agentic workflows.

So next, we'll dive into the fundamentals of harness engineering [harness engineering](hypergolic/docs/harness-engineering.md)
