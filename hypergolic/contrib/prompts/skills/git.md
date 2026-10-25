Land from /app: `git push origin HEAD:<branch>`. It runs the user's gates and review, then confirms or rejects
Describe the merge for its reviewers like a PR body: a succinct summary of what changed and why, 2-3 lines at most, one `-o description=<markdown line>` per line
Pushed commits squash by default; `-o mode=fast-forward` (or project `land_mode="fast-forward"`) keeps them, so `git merge origin/main` updates a PR branch cleanly
