# Hypergolic: Harness Engineering

At this point, you're able to use your harness for project contributions. Out of the box, it might even do about as good a job as any other harness you've used in the past. But the art of harness engineering involves making it easy for the agent to do the right thing. If that appeals to you, read on.

At its most basic, an agentic LLM call has a few simple components:

- **System Prompt**: The context you want to provide to the agent
- **Messages**: The conversation history of your interactions with the LLM
- **Tool Definitions**: An exhaustive list of what you want the agent to be able to do (e.g. read files, or web search)

As we've learned more about how to work with agents, other somewhat-resilient constructs have emerged as useful ways of structuring agentic interaction. Atop `prompts` and `tools` from the schema above, Hypergolic offers a few other building blocks that are a helpful way to think about your agent's operations. Those other blocks are `projects`, `skills`, `roles`, `sandboxes`, and `workflows` which we'll briefly explore here.

Guidance on advanced configuration of each of these can be found in [Advanced Usage](hypergolic/docs/advanced/README.md).

## Projects

Distinct projects help us segment work in ways that are helpful to humans and agents. Contributing to git repos is the primary way humans write code, and agents are similarly trained. Projects also give a boundary to the agent, which is useful for both security and model performance.

```python
from hypergolic import App, Project

app = App()
sample_project = Project(
  id='sample-project',
  name='Sample Project',
  description='An app that I work on',
  git_root=str(Path.home() / "Projects" / "SampleProject")
  ...
)
app.register_project(sample_project)
```

## Tools

As mentioned earlier, a tool is something that you want the agent to be able to do. For example, if you'd like your agent to be able to order a pizza for you, you might define a `pizza` tool within your harness that allows the agent to invoke a `pizza` CLI tool on your laptop.

```python
from hypergolic import App, Tool

app = App()
pizza_tool = Tool(
  id='pizza',
  name='Pizza',
  description='Allows the agent to order a literal pizza via the `pizza` CLI',
  ...
)
```

The description text of tools is made searchable within the agentic sandbox, and the agent is prompted to search for relevant tooling. So if you asked a session to order you a pizza without prompting it on how to do so, it would likely run `apropos pizza`. That `apropos` command searches the text of tool and skill descriptions, and would instruct the agent on how to construct the following tool call:

```bash
pizza order --size=large --toppings=mushroom,anchovies,peppers
```

Tools are perhaps the most important building block in harness engineering, so we'll discuss the parameters of their configuration more extensively in later documentation. For now, just think of them as a way to define what you want the agent to do.

`Tip`: Ask the agent to write itself tools for performing common actions. While the agent can theoretically do anything via the built-in `host_cmd` tool, constructing bespoke tools will save tokens, cut down on review fatigue, and make the agent more autonomous and capable.

## Prompts

Prompts provide the agent with the context and background they need to do your requests. Because prompts consume tokens and context windows, choosing when to disclose information is part of effective prompt/harness engineering.

Within Hypergolic, you can add prompts in several places:

- **System Prompt**: Included at the beginning of every session
- **User Prompt**: Also included in every session, but tailored to your own user preferences. Useful if you share a harness with others.
- **Role Prompt**: The appropriate role prompt is persistently appended to the larger system prompt for each session
- **Project Prompt**: What you want your agent to know about your specific project, whether from a shared source or with your own user-project-specific guidance appended
- **Skill Prompt**: When a skill is activated, the skill's full prompt is added to the context window
- **Workflow Prompt**: Each workflow stage provides a prompt to the agent on that stage's context and objectives

Prompts are unique among Hypergolic building blocks in that they're generally just normal python strings. For modularity and control, you'll likely want to read them from different locations within your file system. Most other constructs accept either `prompt=` or `prompt_path=` parameters that allow you to specify where that context should be read from.

```python
...
app = App()
sample_project = Project(
  ...
  prompt_path=str(Path.home() / "Projects" / "SampleProject" / "Agents.md"),
  ...
)
app.register_project(sample_project)
```

## Skills

A skill can best be thought of as a bundling of a prompt, one or more tools, and any number of sub-skills.

They're used by the agent through a built-in `activate_skill` tool. When a skill is activated, the skill's prompt is exposed to the agent. The associated tool calls are made available to the agent through CLI commands within the agent's sandbox, and sub-skills become searchable and available for activation.

```python
app = App()
dinner_skill = Skill(
  id='dinner',
  name='Dinner',
  description='Guidance on how to help Robert decide what is for dinner',
  prompt="""Taco Tuesday is big in his house, so check if it's Tuesday through the is_tuesday tool. Check with the Chinese food subskill for his favorites.""",
  tools=[is_tuesday, random_meal_suggestion_tool, pizza_tool],
  sub_skills=[chinese_food_preferences_skill],
)
```

## Roles

Each session has a role, which is essentially the "type" of agent you're interacting with. Hypergolic ships with several standard rules (`generalist`, `reviewer`, `worker`, `researcher`) but you can make your own.

```python
project = Project(
  ...
)
finance_role = Role(
  id='finance',
  name='Finance',
  prompt="""You are an expert in business outcomes, strategy, and profit. Politely decline to provide advice outside of finances, suggesting appropriate alternative roles to bring up other questions to."""
  available_skills=[ebitdta_skill, compliance_obligations_skill],
)
project.register_role(finance_role)
```

New sessions can choose which role they want to interact with, and that role persists for the duration of the session. The agentic `dispatch` tool also has the option of dispatching sessions to specific roles.

One example of where you might want to do this is to construct multi-stage agentic reviews that pass through code review, a11y review, brand guideline adherence, and other specific requirements.

Another is if you prefer to interface with agents only on one specific part of your workflow (e.g. planning) and want to have sessions that don't over-extend their focus or "helpfully" offer to do more than you want them to do.

## Sandboxes

Sandboxes are a close second to `tools` in terms of importance, but they're also probably the trickiest building block to get right.

Whenever you start a session, Hypergolic also starts up one or more session-specific containers. Configuration of the sandbox controls available utilities within those containers, what egress is allowed, and more.

```python
project = Project(...)
sample_sandbox = Sandbox(
  containers=[
    SandboxContainer(
      base_image='python:3.15',
      build_steps=[
        'apt install ripgrep',
        ...
      ]
    ),
    ...
  ],
  allowed_egress=[
    'https://pypi.org',
    'https://packages.example.com',
  ]
)
project.register_sandbox(sample_sandbox)
```

Proper sandbox construction lets the agent execute your test suite safely, encodes common conventions, and minimizes the amount of agent-authored code that runs on your host machine.

Sandboxes can also be extensively tuned to try out new forms of agentic interaction. For example: I configure my agentic sandboxes to alias `ls`, such that it appends contents of `AGENTS.md` to the result if one is found in a folder. This saves the agent a turn of listing the directory, and then another turn reading a file it'll almost certainly want to read in my repos.

Developers who customize their shells will respect the inclination to help agents to do the same.

## Workflows

`TODO`: I haven't done much with workflows yet personally, they might not work well. I'm personally excited for what they'll do in the future, but don't leverage them much at the moment. Consider this API particularly likely to change.

Workflows are a static graph of steps that the agent is expected to run through. For example, you may choose to build a Product Feature workflow that guides the agent through what you expect the agent to do when working with you on product ideation.

```python
product_ideation = Workflow(
  id='product_ideation',
  stages=[
    WorkflowStage(id='understand', on_success='critique', ...),
    WorkflowStage(id='critique', on_success='implement', ...),
    WorkflowStage(id='implement', on_success=WorkflowStateChange.DONE),
  ]
)
app.register_workflow(product_ideation)

```

# OLDER

**Tune an approval policy**

> Read-only git commands in my-app keep asking for approval. Change the git tool's policy so status/diff/log/show are auto-approved, destructive commands still ask.

The fastest entry point: press `C` on any approval prompt to open a harness session seeded with that tool call's details, ready to configure its policy.

**Register a project**

> Register my repo at ~/code/billing-service. Explore it, write the project prompt (stack, structure, how to run checks), and set up a sandbox with the app container plus Postgres.

**Build a custom tool**

> Build a `deploy` tool that runs bin/deploy with a staging or production argument. Auto-approve staging; require my approval for production.

**Adjust prompts and roles**

> My reviews keep flagging style nits. Update the reviewer role prompt to focus on correctness and edge cases, not formatting.

**Audit the whole config**

> Run the optimize-config workflow.

The built-in `optimize-config` workflow does a structured pass over your prompts, tools, skills, and workflows and proposes improvements.

- [Configuration](configuration.md) — Full `main.py`, project, and prompt reference
- [Tools](tools.md) — The command surface and approval model
- [Advanced Usage](advanced-usage.md) — Custom tools, sandboxes, MCP, headless runs

## Conclusion

Even if you rarely author these utilities by hand, it's helpful to see what the agent has available for its own configuration.
