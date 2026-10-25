"""Making the agent's own accumulated scripts findable.

``/shared`` persists across every session of a project, which is exactly why it
fills up with what past sessions worked out — a probe, a mirror timing loop, a
note on the package proxy — and exactly why none of it gets reused: a later
session is told the directory exists and nothing about what is in it. The scripts
are capability the harness never declared, so they are invisible to the one-line
index and to ``--help``.

They are indexed here from the file itself: a leading docstring or comment block
is the description, an optional ``tags:`` line is the vocabulary, and the suffix
decides how to run it. Nothing to register and nothing to keep in sync — the
contract is a header comment, which a script worth keeping has anyway.

A subdirectory is only reached if it holds a ``README.md``. Exhaust does not
document itself, so the gate needs no skip list to maintain, and the README a
human reads for progressive disclosure is the same artifact that makes the
directory searchable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from hypergolic.harness.primitives.tool import Tool
from hypergolic.sandbox.shared import shared_dir

#: Marks a command in the search index as a file in ``/shared`` rather than a
#: declared command, so results can say how to run it instead of `--help`.
SHARED_ORIGIN = "shared"

#: Text a session might plausibly reuse. An allowlist, because the directory also
#: collects build logs, backups and other exhaust that would only add noise.
_INDEXED = {".py", ".sh", ".bash", ".zsh", ".md", ".sql", ".js", ".ts", ".rb", ".pl"}

#: What earns a subdirectory a place in the index, and what nothing earns: a
#: vendored tree can hold thousands of indexable suffixes, README or not.
_GATE = "README.md"
_DENIED = {"node_modules", ".git", "__pycache__", ".venv"}

#: Cheap guards on a directory the agent writes freely: a runaway file count or a
#: huge file must not turn discovery into a slow read.
_MAX_FILES = 200
#: Depth below root, and a per-directory share of the window so that one filed-away
#: corner of the tree cannot crowd out every other.
_MAX_DEPTH = 2
_MAX_PER_DIR = 40
_MAX_HEAD = 8192
_MAX_SUMMARY = 200
#: How much of a file with no header is searched. The whole head would let one
#: rambling script weakly match half of everything.
_MAX_FALLBACK = 1024

_TAGS = re.compile(r"^\s*(?:#|\*)?\s*tags\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_UV_SCRIPT_BLOCK = re.compile(r"^#\s*///.*?^#\s*///\s*$", re.DOTALL | re.MULTILINE)


@dataclass(frozen=True)
class SharedScript:
    path: Path
    """Relative to ``/shared``, so nested files run and are identified by where they are."""

    summary: str
    body: str
    tags: list[str]

    @property
    def run(self) -> str:
        """How to run it from the sandbox, where the file is at ``/shared/<path>``."""
        target = f"/shared/{self.path.as_posix()}"
        suffix = self.path.suffix
        if suffix == ".py":
            return f"uv run {target}"
        if suffix in (".sh", ".bash", ".zsh"):
            return f"bash {target}"
        if suffix == ".md":
            return f"cat {target}"
        return target


def _markdown_summary(text: str) -> tuple[str, str]:
    lines = [line.strip() for line in text.splitlines()]
    title = next((line.lstrip("# ").strip() for line in lines if line.startswith("#")), "")
    rest = [line for line in lines if line and not line.startswith("#")]
    first = rest[0] if rest else ""
    return (title or first), text


def _code_summary(text: str) -> tuple[str, str]:
    """The leading docstring, else the leading comment block."""
    stripped = _UV_SCRIPT_BLOCK.sub("", text).lstrip()
    if stripped.startswith("#!"):
        stripped = stripped.partition("\n")[2].lstrip()
    match = re.match(r'(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', stripped, re.DOTALL)
    if match:
        doc = match.group(1).strip()
        head, _, tail = doc.partition("\n")
        return head.strip(), tail.strip()

    comments: list[str] = []
    for line in stripped.splitlines():
        line = line.strip()
        if line.startswith("#!") or not line:
            if comments:
                break
            continue
        if line.startswith("#"):
            comments.append(line.lstrip("#").strip())
            continue
        break
    if not comments:
        return "", ""
    return comments[0], "\n".join(comments[1:])


def _parse(path: Path, root: Path) -> SharedScript | None:
    try:
        text = path.read_text(errors="replace")[:_MAX_HEAD]
    except OSError:
        return None
    summary, body = (
        _markdown_summary(text) if path.suffix == ".md" else _code_summary(text)
    )
    tags = [
        tag.strip().lower()
        for match in _TAGS.findall(summary + "\n" + body)
        for tag in match.split(",")
        if tag.strip()
    ]
    return SharedScript(
        path=path.relative_to(root),
        summary=summary[:_MAX_SUMMARY],
        body=body if summary else text[:_MAX_FALLBACK],
        tags=tags[:12],
    )


def _has_header_shebang(path: Path) -> bool:
    """An extensionless file is only interesting if it declares how to run itself."""
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def _files(directory: Path) -> list[Path]:
    # Filter before capping: the exhaust the allowlist exists to skip would
    # otherwise push real scripts out of the window on name order alone.
    return [
        path
        for path in sorted(directory.iterdir())
        if path.is_file()
        and not path.name.startswith(".")
        and (path.suffix in _INDEXED or (not path.suffix and _has_header_shebang(path)))
    ]


def _documented_dirs(root: Path, depth: int = 1) -> list[Path]:
    if depth > _MAX_DEPTH:
        return []
    found = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.name.startswith(".") or path.name in _DENIED:
            continue
        if not (path / _GATE).is_file():
            continue
        found.append(path)
        found.extend(_documented_dirs(path, depth + 1))
    return found


def scripts(root: Path) -> list[SharedScript]:
    """Files directly in *root*, then those in each subdirectory that documents itself.

    Root first, and directories in name order after it: the tools a session is told
    about live at the top, so they must never be what the window drops.
    """
    if not root.is_dir():
        return []
    found: list[SharedScript] = []
    for directory in [root, *_documented_dirs(root)]:
        for path in _files(directory)[:_MAX_PER_DIR]:
            if len(found) >= _MAX_FILES:
                return found
            parsed = _parse(path, root)
            if parsed is not None:
                found.append(parsed)
    return found


def _display_name(path: Path) -> str:
    """Where a file sits is part of what it is: seven README.md files all named
    "README" would be one entry as far as a reader is concerned."""
    stem = path.stem.replace("_", " ")
    parent = path.parent.name.replace("_", " ")
    return f"{parent} {stem}" if parent else stem


def as_command(script: SharedScript) -> Tool:
    """A search-shaped view of a file, so one ranking covers both kinds of thing.

    Never materialized and never invocable: `/shared` is already on the filesystem
    the agent can run things from, so discovery is the whole job. Giving these a
    shim would mean an approval policy for arbitrary agent-authored code.
    """
    return Tool(
        id=script.path.as_posix(),
        name=_display_name(script.path),
        description=script.summary or "(no header comment — nobody can tell what it does)",
        usage=script.run,
        guidance=script.body,
        tags=script.tags,
        origin=SHARED_ORIGIN,
    )


def shared_commands(project_id: str | None) -> list[Tool]:
    if not project_id:
        return []

    return [as_command(script) for script in scripts(shared_dir(project_id))]
