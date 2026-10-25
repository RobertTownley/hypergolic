/shared persists across this project's sessions; it is a git repo with no branches
- Commit on main and `git push origin main` at once (lands ungated by default); an unpushed commit dies with the session
- `uv run /shared/main.py --help` lists its commands; add reusable scripts there
- Knowledge: /shared/knowledge, curated per `activate_skill knowledge-base`
