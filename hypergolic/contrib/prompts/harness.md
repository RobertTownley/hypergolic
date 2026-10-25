# My Harness

This project is your Hypergolic harness — the user's own `~/.hypergolic/` config. `activate_skill harness-engineering` here for specialized tools and guidance

Edit through your rw /harness clone (commit with git as usual); land with `git push origin main` from /harness; changes take effect after `reload_harness` (`restart` only for hypergolic-package changes)

- `main.py` — entrypoint: `app.use_defaults()` registers the built-ins; customize with `modify_role` / `override_skill` / `override_tool` / `remove_tool`
- `tools/`, `skills/`, `prompts/`, `projects/` — user-owned customizations
- `/hypergolic` — installed Hypergolic source; built-ins load straight from it (nothing is copied into `~/.hypergolic`). Read-only reference — search it for internals

Change a built-in by overriding it in `main.py` — e.g. `app.override_skill("history", prompt_path="~/.hypergolic/prompts/skills/history.md")` pointed at your own file. To change a default for everyone (not just this install), edit the Hypergolic source repo
