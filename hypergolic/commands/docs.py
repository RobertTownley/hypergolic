"""Rendering a command declaration into the docs the agent reads.

``--help`` answers *how*; it is generated from ``usage``, the input and output
schemas, and ``examples``, so it can never drift from what the broker will
accept. ``description`` answers *when*, and is the only thing pushed into the
system prompt.

The README additionally states provenance and approval posture. The latter is
load-bearing for autonomy: an agent that knows which calls will block on a human
can front-load unattended work and batch the gated ones.
"""

from __future__ import annotations

from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from hypergolic.harness.primitives.approval import (
    ApprovalContext,
    ToolApprovalDecision,
    TotalPolicy,
)
from hypergolic.harness.primitives.tool import HOST, SANDBOX, Tool, domain_container


def _type_name(annotation: Any) -> str:
    members = getattr(annotation, "__members__", None)
    if members:
        return "|".join(str(m.value) for m in members.values())
    origin = get_origin(annotation)
    if origin is not None:
        inner = [_type_name(a) for a in get_args(annotation)]
        if origin in (Union, UnionType):
            return "|".join(part for part in inner if part != "NoneType") + (
                "?" if "NoneType" in inner else ""
            )
        origin_name = getattr(origin, "__name__", str(origin))
        return f"{origin_name}[{'|'.join(inner)}]" if inner else origin_name
    return getattr(annotation, "__name__", None) or str(annotation)


def _field_lines(model: type[BaseModel] | None) -> list[str]:
    """Describe inputs from the model, not from a JSON schema dump: ``usage``
    already says how to *pass* them, so all that is left is what each means."""
    if model is None:
        return []
    lines = []
    for name, field in model.model_fields.items():
        bits = [f"- `{name}`", f"({_type_name(field.annotation)})"]
        if not field.is_required():
            bits.append(f"default `{field.get_default(call_default_factory=True)!r}`")
        if field.description:
            bits.append(f"\u2014 {field.description}")
        lines.append(" ".join(bits))
    return lines


def domain_label(command: Tool) -> str:
    if command.domain == HOST:
        return "host (outside the sandbox)"
    if command.domain == SANDBOX:
        return "sandbox (default container)"
    return f"container `{domain_container(command.domain)}`"


def resolved_decision(command: Tool) -> ToolApprovalDecision | None:
    """The command's posture when it can be known without an invocation.

    Only a *total* policy — one ``always()`` built — answers here. Probing an
    arbitrary callable with an empty context would report whatever branch it
    takes when it cannot see the input, which is how a command that gates
    ``--force`` ends up documented as auto-approved. ``None`` means the policy
    classifies per argument, which is a real answer rather than a failure.
    """
    if not command.invocable or not isinstance(command.approval_policy, TotalPolicy):
        return None
    try:
        return command.approval_policy(ApprovalContext(input=None, session=None))
    except Exception:
        return None


def approval_label(command: Tool) -> str:
    if not command.invocable:
        return "n/a \u2014 documentation only"
    decision = resolved_decision(command)
    if decision is None:
        return "depends on the arguments \u2014 read `source` for the policy"
    text = {
        "ALLOW": "auto-approved (no human in the loop)",
        "DENY": "always denied",
        "REQUIRE_APPROVAL": "requires human approval",
    }.get(decision.decision, decision.decision)
    if decision.reason:
        text = f"{text} \u2014 {decision.reason}"
    return text


def readme(command: Tool) -> str:
    """The generated ``/tools/<id>/README.md``, also what ``--help`` prints."""
    lines = [f"# {command.id}", "", command.description, ""]
    if command.tags:
        lines += [f"Tags: {', '.join(command.tags)}", ""]
    if command.invocable:
        lines += ["## Usage", "", "```", command.usage or command.id, "```", ""]
    else:
        lines += [
            "Documentation only \u2014 there is no `/tools/bin/" + command.id + "` to run.",
            "",
        ]

    fields = _field_lines(command.input_schema)
    if fields:
        lines += ["## Arguments", "", *fields, ""]

    out_fields = _field_lines(command.output_schema)
    if out_fields:
        lines += ["## Output", "", *out_fields, ""]

    if command.examples:
        lines += ["## Examples", ""]
        for example in command.examples:
            lines += ["```bash", example.command, "```"]
            if example.note:
                lines += ["", example.note, ""]
            else:
                lines.append("")

    lines += [
        "## Provenance",
        "",
        f"- origin: `{command.origin}`",
    ]
    if command.invocable:
        lines += [
            f"- runs on: {domain_label(command)}",
            f"- approval: {approval_label(command)}",
        ]
    lines.append("")

    if command.guidance:
        lines += ["## Guidance", "", command.guidance.strip(), ""]

    return "\n".join(lines)


def index_line(command: Tool) -> str:
    """One line for ``/tools/index.md`` and the system prompt's relevance index."""
    marker = "" if command.invocable else " (docs only)"
    return f"{command.id}{marker} \u2014 {command.description}"


def index_markdown(commands: dict[str, Tool]) -> str:
    lines = [
        "# /tools",
        "",
        "One directory per command. `bin/<name>` exists when the command is",
        "invocable; a directory without one is documentation. `<name>/README.md`",
        "is what `<name> --help` prints; `<name>/source` symlinks to the real",
        "implementation, so it cannot drift.",
        "",
        "`apropos <what you are trying to do>` searches this list plus the tags,",
        "guidance and examples it does not show.",
        "",
    ]
    for name in sorted(commands):
        lines.append(f"- {index_line(commands[name])}")
    return "\n".join(lines) + "\n"
