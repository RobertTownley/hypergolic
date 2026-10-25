Conduct simulated sessions to test whether a harness change would have changed how a past task went. You are the conductor: you start the session, play the user, and answer every gated tool call. Nothing you mock runs on the user's machine

## Set the conditions
Find the source session with `history`: its recorded shas (`sessions.repo_shas`), opening prompt, the user's later replies, and the approval feedback (`tool_approvals`: denials, inline comments). Then dispatch a child with `--eval`, the old app sha, and the harness/shared version under test:

`dispatch "<opening prompt>" --eval --project <source project> --tier <source tier> --pins '{"app":"<sha>","harness":"main","shared":"main"}'`

`--eval` leaves out the child rules prompt; the child is a generalist (the dispatch default), so it acts like a session the user started. `--project` lets you conduct a session from any project, so you need not start a conductor there first. Do not pass a role unless the source session had it. A harness pin needs the user's approval. To test an App setting without a harness commit, add its flag, e.g. `--strip-history-thinking=false` (see `dispatch --help`)

## Conduct
`activate_skill conducting-simulations` to learn how to conduct a simulation, before you run the `dispatch` command

## Compare
Put the replay and the source side by side: turns, time, tokens, cost, questions asked, points where the user (or you) had to correct the child, and the final diff. Name what changed and whether the harness change caused it. One run is an anecdote — say so before you conclude
