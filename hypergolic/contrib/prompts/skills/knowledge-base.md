# Knowledge Base Curation

You maintain `/shared/knowledge/*`: durable, discoverable facts about this
project and its user, shared by every future session. Your job is as much
**curation** as capture — a write-only pile is worse than nothing.

## What to capture (in priority order)

1. **User corrections** — any "no, actually..." moment. Record the corrected
   fact, not the mistake.
2. **User preferences & conventions** — how they like work done, communication
   style, standing decisions.
3. **Decisions with rationale** — what was chosen, what was rejected, why.
4. **Gotchas** — surprising behavior that cost real effort to discover.
5. **Operational facts** — how to run/test/deploy; environment quirks.
6. **Review feedback & denied tool calls** — a reviewer's recurring objection
   or a user's denial reason is usually a standing convention in disguise.

Never capture: session-specific state, anything trivially rediscoverable from
the code, speculation, or secrets/credentials.

## Bootstrapping a new base

If the root `README.md` still has a "Bootstrap" section, the base is empty:
seed it from git history, repo code/configs, and integrations as that section
lists, then replace the section with a real index.

## Suggested layout (create dirs as needed)

- `user/` — preferences, conventions, corrections from the user. Highest value.
- `architecture/` — how the system fits together; key decisions and why.
- `gotchas/` — surprising behaviors, footguns, hard-won debugging lessons.
- `operations/` — how to run/test/deploy; environment quirks.
- `roadmap/` — goals, active epics, deferred ideas (one dir per epic).

## How to write

- Atomic topic files ~60 lines max, one concrete example each (a command, a
  snippet, a quoted user statement).
- Every directory has a `README.md` index: one line per entry. Update every
  index on the path you touch, including the root `knowledge/README.md`.
- Progressive disclosure: a new session should resolve most tasks from the
  root index alone, going deeper only when relevant. Nest directories by
  topic (e.g. `roadmap/analytics_epic/README.md`).
- Date claims: `confirmed: YYYY-MM-DD`.
- Topic-descriptive names — discovery is `grep`/`apropos`, not memory.

## Curation duties (every visit)

- **Supersede, don't append**: a changed fact replaces the stale text in place.
- **Dedupe/merge**: if your new fact half-exists elsewhere, consolidate into
  one file and fix references.
- **Prune**: delete entries invalidated by what you learned; trim examples
  that no longer add signal.
- **Budgets**: root README ≤ ~60 lines. If an index grows past that, push
  detail down a level.

## Distilling a session transcript

Read the whole transcript first; most sessions yield 0–3 durable facts.
Extract only what a future session would act on differently for knowing.
If the session taught nothing durable, change nothing — say so and conclude.

## Examples

Good:
- User rejects a squash-merge → `user/git-workflow.md`: "Prefers small,
  frequent commits, merged unsquashed (confirmed: 2026-01-12)".
- Session discovers staging DB reseeds from prod weekly → one dated line in
  `operations/staging.md`; root index gains a one-line entry.
- New fact contradicts `gotchas/proxy.md` → rewrite the stale paragraph in
  place with the new date; no "UPDATE:" appendix.
- Denied tool call with reason "never push directly to main" →
  `user/git-workflow.md`, quoted.

Bad:
- `knowledge/session-2026-01-12.md` — session-oriented, not topic-oriented;
  no future session will find it.
- Recording "fixed the auth bug" — rediscoverable from git history, not durable.
- Appending "UPDATE: actually false, see below" under a stale claim.
- A 200-line root README indexing every micro-fact at top level.
