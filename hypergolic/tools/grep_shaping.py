"""Regroup grep-style tool output to avoid repeating file paths.

Shell output frequently contains ``path:lineno:text`` match lines (grep -rn,
rg's default format) where the same path is repeated on every line. Runs of
such lines are regrouped ag-style — path once as a header, ``lineno:text``
beneath, blank line between files — which can save substantial tokens on
wide searches. Everything else passes through verbatim.

Wrapped for ToolResults (with gating) in output_shaping.
"""

from __future__ import annotations

import re


# Path portion must contain "/" or "." and start with a non-space so that
# e.g. timestamps ("12:34:56 ...") never parse as matches. Bare extensionless
# names (Makefile:5:...) deliberately fail this and pass through verbatim.
_MATCH_LINE = re.compile(r"^(?=\S)([^:\n]*[./][^:\n]*):(\d+):(.*)$")

_MIN_RUN = 3


def _flush(run: list[tuple[str, str, str]], out: list[str]) -> None:
    if not run:
        return
    paths = [p for p, _, _ in run]
    # Reshaping only pays off when a path repeats; otherwise the header
    # format is strictly longer.
    if len(run) < _MIN_RUN or len(set(paths)) == len(run):
        out.extend(f"{p}:{n}:{t}" for p, n, t in run)
    else:
        groups: dict[str, list[str]] = {}
        for p, n, t in run:
            groups.setdefault(p, []).append(f"{n}:{t}")
        out.append("\n\n".join(f"{p}\n" + "\n".join(hits) for p, hits in groups.items()))
    run.clear()


def shape_grep_text(text: str) -> str:
    out: list[str] = []
    run: list[tuple[str, str, str]] = []
    for line in text.split("\n"):
        m = _MATCH_LINE.match(line)
        if m:
            run.append((m.group(1), m.group(2), m.group(3)))
        else:
            _flush(run, out)
            out.append(line)
    _flush(run, out)
    return "\n".join(out)
