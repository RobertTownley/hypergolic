"""Startup validation over the structured harness.

The harness is Python at import time, so materialization can fail loudly rather
than degrade. Two checks are load-bearing rather than merely tidy:

``bin/`` is a flat, single namespace, matching how ``PATH`` actually resolves — so
two skills cannot ship the same command name, and origin has to be metadata
rather than hierarchy.

``/tools/bin`` precedes the image's own directories, so a command named ``test``
would shadow a real binary the shell depends on. The precedence is what makes the
collision rule a correctness requirement rather than a packaging detail.
"""

from __future__ import annotations

from hypergolic.harness.primitives.tool import HOST, SANDBOX, Tool, domain_container

#: Names ``/tools/bin`` must never shadow: shell builtins and the utilities a
#: non-interactive ``sh -c`` line is built out of. Deliberately does not include
#: names a command legitimately replaces — ``git`` shadows shell git on purpose,
#: because a worktree's git metadata lives on the host outside the mount.
RESERVED_NAMES = frozenset(
    {
        "[", "awk", "basename", "cat", "cd", "chmod", "cp", "cut", "dirname",
        "echo", "env", "eval", "exec", "exit", "export", "expr", "false",
        "find", "grep", "head", "kill", "ln", "ls", "mkdir", "mv", "printf",
        "pwd", "read", "rm", "sed", "set", "sh", "sleep", "sort", "tail",
        "tee", "test", "touch", "tr", "true", "uniq", "wc", "which", "xargs",
    }
)


class CommandValidationError(Exception):
    """One or more command declarations cannot be materialized."""


def validate_commands(
    commands: list[Tool], *, known_containers: set[str] | None = None
) -> list[str]:
    """Return every problem found. Empty means the set can be materialized."""
    problems: list[str] = []

    seen: dict[str, Tool] = {}
    for command in commands:
        existing = seen.get(command.id)
        if existing is not None:
            problems.append(
                f"duplicate command id '{command.id}': declared by "
                f"'{existing.origin}' and '{command.origin}'"
            )
            continue
        seen[command.id] = command

        if command.invocable and command.id in RESERVED_NAMES:
            problems.append(
                f"command '{command.id}' would shadow a binary the shell depends "
                f"on, because /tools/bin precedes /usr/bin on PATH"
            )
        if "/" in command.id or command.id.startswith("."):
            problems.append(
                f"command id '{command.id}' is not usable as a filename in /tools/bin"
            )
        if command.invocable and not command.description.strip():
            problems.append(
                f"command '{command.id}' has no description, so it cannot appear "
                f"in the relevance index and the agent has no way to know when to "
                f"reach for it"
            )
        if command.input_schema is not None:
            try:
                command.input_schema.model_json_schema()
            except Exception as exc:
                problems.append(f"command '{command.id}' input_schema is invalid: {exc}")
        if command.output_schema is not None:
            try:
                command.output_schema.model_json_schema()
            except Exception as exc:
                problems.append(f"command '{command.id}' output_schema is invalid: {exc}")

        target = domain_container(command.domain)
        if command.domain not in (HOST, SANDBOX) and target is None:
            problems.append(f"command '{command.id}' has invalid domain '{command.domain}'")
        elif target is not None and known_containers is not None and target not in known_containers:
            problems.append(
                f"command '{command.id}' targets container '{target}', which this "
                f"session does not declare (has: {sorted(known_containers) or 'none'})"
            )

    return problems


def assert_valid(commands: list[Tool], *, known_containers: set[str] | None = None) -> None:
    problems = validate_commands(commands, known_containers=known_containers)
    if problems:
        raise CommandValidationError(
            "Tool declarations cannot be materialized:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
        )
