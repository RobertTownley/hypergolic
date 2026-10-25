Split work across child sessions and integrate what they return. You own your sandbox; the user owns their machine. A child's gated calls come to you, and the harness lets you approve only merges into your own sandbox

## Start a child
`dispatch <role> "<prompt>" [--tier T] [--attach PATH] [--pins JSON] [--no-wait]`
- The child's repo is cut from your committed tip: commit first. Uncommitted work does not travel
- The prompt is its whole spec. Name the goal, the files, the checks it must run, and what to hand back
- `--pins '{"app":"<sha>"}'` roots the child at that sha on a pin branch in your sandbox
- `--no-wait` returns at once; read its work later with `history`. Without it, your call blocks until the child needs you

## When your `dispatch` call returns
- **Approval request** → `dispatch --resume <request> --outcome <o> [--message TEXT]`, then you wait on the child again:
  - `approve` — only an app merge into the child's base (your branch or its pin branch). The harness refuses anything else
  - `deny --message '<reason>'` — the child sees your reason, as if from a reviewer
  - `escalate` — sends it to the user. Use for anything that touches the host: harness/shared changes, host commands, external writes
  - `mock --result '<text>' [--error]` — the call does not run; the child gets your text as its result
- **Conclusion** → the child called `conclude`. Its committed work survives for `diff_child`/`merge_child`
- **End of turn** (`--eval` children) → reply with `dispatch --reply <child> "<text>"`, or end it

## Merges into your branch
A child pushes `git push origin HEAD:main` like any session (it sees your base name). The harness runs the same gates, sends the approval to you, and merges into your sandbox: a fast-forward, or a merge that leaves your uncommitted edits alone. If the merge would overwrite your local edits, the push fails with the reason; commit, then let the child push again. Pushes to any other branch go to the user

## End a child
`dispatch --conclude <child> [--keep-branch]` ends a child that is not running; the child need not call `conclude`. `--keep-branch` keeps its branch for `diff_child`/`merge_child`. Your own conclusion ends your open children and removes their host refs

## Sub-skills
- `evaluation` — conduct a simulated session: replay a past task at old shas, play the user and the gated tools, compare with the source session
