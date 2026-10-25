"""Regroup runs of bare path lines by directory to avoid repeating prefixes.

File-list output (grep -l, fd, find, git ls-files) repeats directory
prefixes on every line. Runs of whole-line paths are regrouped — dirname
once as a ``dir/`` header, basenames beneath, blank line between groups —
mirroring grep_shaping. Full paths reconstruct by concatenating header +
name. Lines within a run may be reordered (grouped by first-seen dir).
Everything else passes through verbatim.
"""

from __future__ import annotations

import re

# Entire line must be one path token: no whitespace or ":" (rules out
# prose, diffs, URLs, grep matches) and at least one "/" with a non-empty
# final segment.
_PATH_LINE = re.compile(r"^[^\s:]*/[^\s:/]+$")

_MIN_RUN = 3


def _flush(run: list[str], out: list[str]) -> bool:
    """Emit *run*; True if the emitted text ends with a dir/ block."""
    if not run:
        return False
    dirs = [p.rsplit("/", 1)[0] + "/" for p in run]
    if len(run) < _MIN_RUN or len(set(dirs)) == len(run):
        out.extend(run)
        run.clear()
        return False
    else:
        groups: dict[str, list[str]] = {}
        for d, p in zip(dirs, run):
            groups.setdefault(d, []).append(p[len(d):])
        # Blank lines delimit multi-file blocks; singletons stay plain lines.
        text = ""
        prev_block = False
        for d, names in groups.items():
            block = len(names) > 1
            if text:
                text += "\n\n" if block or prev_block else "\n"
            text += f"{d}\n" + "\n".join(names) if block else d + names[0]
            prev_block = block
        out.append(text)
    run.clear()
    return prev_block


def shape_path_list_text(text: str) -> str:
    out: list[str] = []
    run: list[str] = []
    for line in text.split("\n"):
        if _PATH_LINE.match(line):
            run.append(line)
        else:
            # Blank line after a block so *line* can't read as a basename.
            if _flush(run, out) and line:
                out.append("")
            out.append(line)
    _flush(run, out)
    return "\n".join(out)
