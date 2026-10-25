"""Host-side repair of ``edit FILE <<DELIM`` heredocs before the shell sees them.

The ``cmd`` tool hands the agent's line to ``sh -c`` as one argv element, so
the shell parses exactly what the agent wrote. For ``edit`` that is a liability
twice over: an unquoted delimiter lets ``$x`` and backticks expand inside what
is always literal file text, and a bare delimiter line inside a hunk ends the
heredoc early — the shell then runs the rest of the file content as commands.

Because we own the hunk grammar (``<<<<`` / ``====`` / ``>>>>``) the host can
tell a content line from the terminator without guessing: a delimiter line
inside an open hunk cannot be the terminator, since that would leave the hunk
unterminated. So the host quotes the delimiter, and swaps it for an unused one
when the body collides. Generic ``cat >`` / ``python3 -`` heredocs have no such
grammar and are left alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from hypergolic.sandbox.edit import CLOSE, OPEN, SEP

# `edit` in command position (line start or after ; & | ( $( ), optionally
# path-prefixed, followed by a heredoc redirect. Group 1: the whole `<<` token,
# 2: dash, 3: quote char or '', 4: delimiter word.
_EDIT_HEREDOC = re.compile(
    r"(?:^|[;&|(])\s*(?:\S*/)?edit\s[^\n]*?(<<(-?)\s*(['\"]?)(\w+)\3)"
)
_FRESH = "HG_EOF"


@dataclass
class _Heredoc:
    open_line: int
    close_line: int | None
    dash: bool
    quoted: bool
    delim: str
    collisions: list[int]


def _scan_body(lines: list[str], start: int, delim: str, dash: bool) -> tuple[int | None, list[int]]:
    """Walk hunk state from ``start``; return (terminator line index, collision
    line indexes). The terminator is the first delimiter line seen outside a
    hunk; delimiter lines inside a hunk are content the shell would mistake."""
    state = "outside"
    collisions: list[int] = []
    for i in range(start, len(lines)):
        line = lines[i].lstrip("\t") if dash else lines[i]
        if line == delim:
            if state == "outside":
                return i, collisions
            collisions.append(i)
            continue
        marker = line.rstrip()
        if marker == OPEN:
            state = "old"
        elif marker == SEP and state == "old":
            state = "new"
        elif marker == CLOSE:
            state = "outside"
    return None, collisions


def _fresh_delim(lines: list[str]) -> str:
    taken = {line.strip() for line in lines}
    delim, n = _FRESH, 1
    while delim in taken:
        n += 1
        delim = f"{_FRESH}{n}"
    return delim


def prepare_edit_heredocs(command: str) -> tuple[str, list[str]]:
    """Return ``command`` with every ``edit`` heredoc made safe, plus one note
    per repair for the agent. Unchanged commands come back with no notes."""
    lines = command.split("\n")
    notes: list[str] = []
    i = 0
    while i < len(lines):
        m = _EDIT_HEREDOC.search(lines[i])
        if not m:
            i += 1
            continue
        dash, quote, delim = m.group(2) == "-", m.group(3), m.group(4)
        close, collisions = _scan_body(lines, i + 1, delim, dash)
        if close is None:
            # No terminator anywhere; let the shell report it as written.
            i += 1
            continue
        new_delim = delim
        if collisions:
            new_delim = _fresh_delim(lines)
            at = ", ".join(str(c + 1) for c in collisions)
            notes.append(
                f"heredoc delimiter `{delim}` also appears inside a hunk (line {at}); "
                f"ran with `<<'{new_delim}'` so the body stayed whole"
            )
            indent = lines[close][: len(lines[close]) - len(lines[close].lstrip("\t"))] if dash else ""
            lines[close] = indent + new_delim
        elif not quote:
            notes.append(f"quoted heredoc delimiter `{delim}` so hunk text stays literal")
        if collisions or not quote:
            token = f"<<{'-' if dash else ''}'{new_delim}'"
            lines[i] = lines[i][: m.start(1)] + token + lines[i][m.end(1):]
        i = close + 1
    return "\n".join(lines), notes
