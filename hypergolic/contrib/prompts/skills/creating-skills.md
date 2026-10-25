# Creating Skills
Skills are the harness building block for letting agents uncover core knowledge. Without them, knowledge is provided in lengthy system prompts, wasting tokens and context, or worse: never provided

## Progressive Discovery
Skill architecture needs to consider how the agent will discover the skill. A good skill is discoverable through `apropos` and succinctly-searchable source documentation in /hypergolic. Even more importantly, there's an anticipated path through the top level. Example:
- System prompt: "`activate_skill git` to land work"
- `git` skill: activation lists its sub-skill `git-pr`, for opening a pull request
- `git-pr` sub-skill: the process for opening a pull request

## Prompting
Ref `activate_skill writing-prompts` for more guidance. Additionally, avoid duplicating content between skills that will be progressively discovered. Activating a skill informs the agent of available sub-skills, so keep names self-documenting

## Tooling
Reference links to tooling used/needed as part of this skill. For this one:
- `Skill(id, tags, name, description, prompt_path, tools, skills=[...])`: /hypergolic/harness/primitives/bundles.py
- User skills: /harness/skills. Built-ins: /hypergolic/contrib/skills/registry.py; change one with `app.override_skill`
- `apropos` searches tags and description
