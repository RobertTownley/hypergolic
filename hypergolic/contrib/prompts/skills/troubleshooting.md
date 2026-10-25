# Skill: Troubleshooting

Not for issues in the user's project — for your own operations and tooling. If your execution environment confuses you or your tools aren't fluidly enabling your goals, that is a first-priority problem. Never work around an issue without durably fixing it, and never ignore one because it's pre-existing.

Communicate under these headings so the user can follow the debugging process.

## Step 1: State
Say what you're trying to do, what you expected, and specifically what's going wrong.

## Step 2: Diagnose
This is a custom harness and may be misconfigured for the task in front of it (e.g. `python -m pytest` fails because the app is tooled for `uv run`).
- Check /shared/* and run `history` queries: have other agents hit this before?
- `cat /tools/<name>/source` shows a failing command's code and approval policy
- Tail /harness/errors.log if something crashed
- Sandbox hanging or failing to start? `activate_skill harness-checkup`
- Then `activate_skill harness-engineering` and examine the configuration in /harness
- If none of this clearly reveals the cause, ask the user for ideas, alongside an offer to investigate further

## Step 3: Fix
Choose the ideal long-term solution, not the nearest workaround: install the missing dependency, repair the tool at its source, correct the configuration.

## Step 4: Prevent
Once unblocked, ensure other agents never hit this. Most issues are one-offs — adding your specific issue to every future session's context is a disservice. Choose the discoverable home:
- A skill tagged with the words a stuck agent would search (`venv`, `pytest`, ...)
- A /shared script or doc with a searchable header
- A system-prompt line plus a sandbox fix, only if truly universal (e.g. prompt "use `uv`" and ensure `uv` is in the image)

Success requires both: you're unblocked, and the issue can't silently recur.
