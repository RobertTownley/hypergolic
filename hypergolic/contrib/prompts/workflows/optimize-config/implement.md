You are executing an approved optimization proposal

## How to implement

Work through the approved proposal systematically, in priority order. For each change:
1. Explain what you're about to do
2. Make the change
3. Verify it worked
4. Move to the next change

## Tools to use

- **`edit` / `write`** — for `~/.hypergolic/main.py` (registrations) and all prompt files, tool scripts, and skill prompts
- **`cat`** — verify changes after making them
- **`validate_harness`** — after editing `main.py`, confirm the harness still loads and is well-formed
- **`restart`** — once changes are validated, if the user wants them live this session

## Guidelines

- One logical change at a time; don't batch unrelated changes
- After writing a tool script, verify the file exists and looks correct
- After registering a tool in config, read the config back to confirm it's valid
- If a change fails or produces unexpected results, explain what happened and ask the user how to proceed rather than guessing
- Track everything: what was done, what was skipped (and why), and any issues encountered
- If the user wants to skip or modify a proposed change, respect that and note it

## What to produce

- **summary**: Narrative of what was implemented
- **changes_made**: Changes successfully applied
- **changes_skipped**: Changes skipped, with reasons
- **issues_encountered**: Any problems during implementation
