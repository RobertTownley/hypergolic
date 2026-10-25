"""Output a tool guarantees the model sees.

Broker-side tools (the land gate, review) reach the model only through the
agent's own shell, where a pipe like ``git push 2>&1 | tail -2`` can destroy
the output — denial feedback included. Text posted here is appended verbatim
to the session's next completed tool result, after truncation, so no shell
pipeline can eat it. Entries already visible in the result (modulo git's
``remote:`` prefixing) are skipped.

With parallel tool calls, a concurrently completing tool may drain an entry
posted for a sibling — the model still sees it, just attached elsewhere.
Entries for sessions that end without another tool call are retained for the
process lifetime; accepted, they are tiny strings.
"""

from __future__ import annotations

import threading

from hypergolic.harness.primitives.results import ToolResult

_HEADER = (
    "\n[delivered by the harness: output a tool guaranteed you would see, "
    "even if a shell pipeline truncated it]\n"
)

_lock = threading.Lock()
_pending: dict[str, list[str]] = {}


def post(session_id: str, text: str) -> None:
    if not text.strip():
        return
    with _lock:
        _pending.setdefault(session_id, []).append(text)


def drain(session_id: str) -> list[str]:
    with _lock:
        return _pending.pop(session_id, [])


def _lines(text: str) -> set[str]:
    out = set()
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("remote:"):
            line = line[len("remote:"):].strip()
        if line:
            out.add(line)
    return out


def append_pending(output: ToolResult, session_id: str) -> ToolResult:
    for text in drain(session_id):
        visible = _lines("\n".join(b["text"] for b in output.iter_text_blocks()))
        if _lines(text) <= visible:
            continue
        output = output.append_text(_HEADER + text.strip() + "\n")
    return output
