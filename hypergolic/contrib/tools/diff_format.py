"""Shared policy for presenting branch diffs to agents token-efficiently.

Inline a diff only when small, always exclude lock/generated files from
the inline body (they stay visible in ``--stat``), and otherwise direct
the agent to fetch what it needs with git in its own sandbox.
"""
from __future__ import annotations

MAX_INLINE_DIFF_CHARS = 30_000

#: Generated files excluded from inline diffs (still visible in the stat).
EXCLUDED_PATHSPECS = (
    ":(exclude)*.lock",
    ":(exclude)*-lock.json",
    ":(exclude)*-lock.yaml",
    ":(exclude)go.sum",
)

EXCLUDED_NOTE = (
    "Lock/generated files (`*.lock`, `*-lock.json`, `*-lock.yaml`, `go.sum`) "
    "are excluded here but visible in the stat above."
)


def fetch_diff_instruction(
    span: str, diff_is_empty: bool, pre_command: str | None = None,
) -> str:
    """Tell the reading agent how to pull the diff itself.

    ``pre_command`` prefixes a required setup step (e.g. fetching a ref from
    the read-only host-repo mount into the reader's own clone).
    """
    reason = (
        "Only lock/generated files changed, which are not inlined"
        if diff_is_empty
        else "Too large to inline"
    )
    command = f"git diff {span}"
    if pre_command:
        command = f"{pre_command} && {command}"
    return (
        f"{reason}. Fetch the diff yourself: "
        f"`{command}`, narrowed per file with `-- <path>`."
    )
