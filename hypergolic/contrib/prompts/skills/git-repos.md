The sandbox has three git repos; git acts on the one you run it from, so cd there first
- /app: the user's project
- /shared: scripts and knowledge that persist across sessions. `activate_skill shared`
- /harness: session clone of the user's Hypergolic config. Commit, then `git push origin main` from /harness; changes take effect after `reload_harness` (no process restart)
