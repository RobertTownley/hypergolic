"""``edit``: anchored search/replace for files inside the sandbox.

Every workspace image gets ``/usr/local/bin/edit`` (see ``REQUIRED_BUILD_STEPS``),
a one-line wrapper that runs this file with ``hg-python`` through the read-only
``/hypergolic`` mount — so the tool ships with the package and changes without
an image rebuild. Stdlib only, no package imports: it runs where the package is
a mount, not an install.

Why it exists: session history showed most file edits as ``python3 - <<'EOF'``
scripts of ``open().read()`` / ``s.replace(old, new)`` / ``open('w').write()``,
each paying ~260 chars of boilerplate plus a share of quoting bugs and silent
no-op replaces. A quoted heredoc of ``<<<< old ==== new >>>>`` hunks carries
any text unescaped, and a hunk that matches zero or several times fails loudly
instead of writing the wrong thing.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from typing import TextIO

OPEN, SEP, CLOSE = "<<<<", "====", ">>>>"

USAGE = f"""edit [--all] [--diff] FILE <<'EOF'
{OPEN}
text to find (exact, must match once)
{SEP}
replacement text
{CLOSE}
EOF

Any number of hunks per call, applied in order; the file is written only if
every hunk applies. An empty replacement deletes the text. The find text must
match exactly one place; pass --all to replace every match instead. --diff
prints the resulting unified diff. New files: use `cat > FILE <<'EOF'`."""


class EditError(Exception):
    pass


def parse_hunks(text: str) -> list[tuple[str, str]]:
    hunks: list[tuple[str, str]] = []
    old: list[str] | None = None
    new: list[str] | None = None
    for n, line in enumerate(text.split("\n"), 1):
        marker = line.rstrip()
        if marker == OPEN:
            if old is not None:
                raise EditError(f"line {n}: {OPEN} inside an open hunk (missing {CLOSE}?)")
            old, new = [], None
        elif marker == SEP:
            if old is None or new is not None:
                raise EditError(f"line {n}: {SEP} outside a hunk")
            new = []
        elif marker == CLOSE:
            if old is None or new is None:
                raise EditError(f"line {n}: {CLOSE} before {SEP}")
            if not old:
                raise EditError(f"line {n}: empty find text; use `cat >` to write a whole file")
            hunks.append(("\n".join(old), "\n".join(new)))
            old = new = None
        elif new is not None:
            new.append(line)
        elif old is not None:
            old.append(line)
        elif line.strip():
            raise EditError(f"line {n}: text outside a hunk (expected {OPEN})")
    if old is not None:
        raise EditError(
            f"unterminated hunk (missing {CLOSE}); if the hunk text has a line equal to "
            "your heredoc delimiter, the shell ended the heredoc there - use another delimiter"
        )
    if not hunks:
        raise EditError(f"no hunks on stdin\n\n{USAGE}")
    return hunks


def _locate(text: str, old: str) -> str:
    """Why a hunk found nothing: the longest partial match and where it diverged."""
    lines, want = text.split("\n"), old.split("\n")
    best = (0, -1)
    for i, line in enumerate(lines):
        if line != want[0]:
            continue
        k = 1
        while k < len(want) and i + k < len(lines) and lines[i + k] == want[k]:
            k += 1
        best = max(best, (k, i))
    k, i = best
    if k == 0:
        loose = [n for n, line in enumerate(lines, 1) if line.strip() == want[0].strip()]
        if loose:
            return f"first line found only with different whitespace at line {', '.join(map(str, loose))}"
        return "first line not found in file"
    if k == len(want):
        return f"matches at line {i + 1} only with different whitespace"
    return (
        f"lines {i + 1}-{i + k} match the first {k} of {len(want)} find lines; "
        f"line {i + k + 1} differs:\n  file: {lines[i + k] if i + k < len(lines) else '<EOF>'!r}"
        f"\n  find: {want[k]!r}"
    )


def apply_hunks(text: str, hunks: list[tuple[str, str]], *, all_: bool = False) -> str:
    for n, (old, new) in enumerate(hunks, 1):
        count = text.count(old)
        if count == 0:
            raise EditError(f"hunk {n}: no match; {_locate(text, old)}")
        if count > 1 and not all_:
            raise EditError(f"hunk {n}: {count} matches; add context to make it unique, or --all")
        text = text.replace(old, new)
    return text


def main(argv: list[str], stdin: TextIO, stdout: TextIO, stderr: TextIO) -> int:
    parser = argparse.ArgumentParser(prog="edit", usage=USAGE, add_help=True)
    parser.add_argument("file")
    parser.add_argument("--all", action="store_true", help="replace every match of each hunk")
    parser.add_argument("--diff", action="store_true", help="print the unified diff after writing")
    args = parser.parse_args(argv)
    try:
        hunks = parse_hunks(stdin.read())
        try:
            with open(args.file, encoding="utf-8", newline="") as fh:
                before = fh.read()
        except OSError as exc:
            raise EditError(f"{args.file}: {exc.strerror}") from exc
        after = apply_hunks(before, hunks, all_=args.all)
    except EditError as exc:
        print(f"edit: {exc}", file=stderr)
        return 1
    with open(args.file, "w", encoding="utf-8", newline="") as fh:
        fh.write(after)
    n = len(hunks)
    print(f"{args.file}: {n} hunk{'s' if n != 1 else ''} applied", file=stdout)
    if args.diff:
        stdout.writelines(
            difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                args.file, args.file,
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], sys.stdin, sys.stdout, sys.stderr))
