"""Per-command argv parsers: `git log --oneline` instead of
`{"operation": "log", "args": ["--oneline"]}`.

Each parser returns the command's real input model. Commands absent from
a declared ``Tool.argv`` get one inferred from their schema shape.
"""

from __future__ import annotations

import json
import shlex
from enum import Enum
from typing import Any, Iterable, get_args

from pydantic import BaseModel

from hypergolic.commands.parsers import (
    ParserBuilder,
    ParseFn,
    UsageError,
    json_arg,
    no_args,
    validate,
)
from hypergolic.commands.parsers import take_flags as flags_of
from hypergolic.pins.app_overrides import OVERRIDE_FIELDS


def _required(model: type[BaseModel] | None) -> type[BaseModel]:
    assert model is not None, "parser requires an input schema"
    return model


def positional(
    *names: str,
    joined: str | None = None,
    bools: Iterable[str] = (),
    values: Iterable[str] = (),
    multi: Iterable[str] = (),
    remap: dict[str, str] | None = None,
    negated: Iterable[str] = (),
) -> ParserBuilder:
    """Leading positionals, optional joined prose tail, flags.

    *joined* names the field that soaks up all remaining positionals as one
    space-joined string (a commit message, a prompt). *remap* renames a flag
    onto a differently-named field; *negated* flags set their field ``False``.
    """
    bool_names = set(bools) | set(negated)
    rename = dict(remap or {})
    falsey = set(negated)

    def build(model: type[BaseModel] | None) -> ParseFn:
        schema = _required(model)

        def parse(args: list[str]) -> BaseModel | None:
            flags, rest = flags_of(
                args, bools=bool_names, values=values, multi=multi
            )
            payload: dict[str, Any] = {}
            for key, value in flags.items():
                payload[rename.get(key, key)] = False if key in falsey else value
            for name in names:
                if not rest:
                    break
                payload[name] = rest.pop(0)
            if joined and rest:
                payload[joined] = " ".join(rest)
                rest = []
            if rest:
                raise UsageError(f"got unexpected extra arguments {rest!r}.")
            return validate(schema, payload)

        return parse

    return build


def passthrough(field: str) -> ParserBuilder:
    """The argv tail *is* a list field, token for token.

    The right shape for wrappers around a real CLI (`gh pr list --json url`),
    where flags belong to the wrapped program, not to us.
    """

    def build(model: type[BaseModel] | None) -> ParseFn:
        schema = _required(model)

        def parse(args: list[str]) -> BaseModel | None:
            return validate(schema, {field: args})

        return parse

    return build


def joined_tail(field: str, *, required: bool = True) -> ParserBuilder:
    """The whole tail is one space-joined string field."""

    def build(model: type[BaseModel] | None) -> ParseFn:
        schema = _required(model)

        def parse(args: list[str]) -> BaseModel | None:
            if not args:
                if required:
                    raise UsageError(f"expects a {field.replace('_', ' ')}.")
                return validate(schema, {})
            return validate(schema, {field: " ".join(args)})

        return parse

    return build


def dispatch_argv(model: type[BaseModel] | None) -> ParseFn:
    """`dispatch [<role>] <prompt...> [--tier T] [--attach PATH ...] [--standalone]
    [--project P] [--base B] [--no-wait] [--pins JSON] [--eval] [--<app setting>=VALUE]`,
    `dispatch --reply <child> <text...>`, `dispatch --conclude <child> [--keep-branch]`, or
    `dispatch --resume <request> --outcome approve|deny|escalate|mock [--message TEXT]
    [--result TEXT [--error]]`.

    Operations on an existing child are flags, never a leading word, so positional
    text is always a prompt or reply: `dispatch reply to this` dispatches that prompt.
    """
    schema = _required(model)
    roles = _enum_values(schema.model_fields["role"].annotation)

    def parse(args: list[str]) -> BaseModel | None:
        flags, rest = flags_of(
            args,
            bools={"standalone", "no_wait", "eval", "keep_branch", "error"},
            values={
                "tier", "project", "base", "pins", "reply", "conclude", "resume", "outcome", "message", "result",
                *OVERRIDE_FIELDS,
            },
            multi={"attach"},
        )
        ops = [op for op in ("reply", "conclude", "resume") if op in flags]
        if len(ops) > 1:
            raise UsageError("use one of --reply, --conclude, --resume.")
        if ops == ["resume"]:
            return _parse_resume(flags, rest)
        if ops == ["conclude"]:
            if rest:
                raise UsageError("--conclude expects `<child> [--keep-branch]` and no text.")
            return validate(schema, {"conclude": flags["conclude"], "keep_branch": "keep_branch" in flags})
        if ops == ["reply"]:
            if not rest:
                raise UsageError("--reply expects `<child> <text...>`.")
            return validate(schema, {"reply": flags["reply"], "prompt": " ".join(rest)})
        payload: dict[str, Any] = {}
        if rest and rest[0] in roles:
            payload["role"], *rest = rest
        if rest:
            payload["prompt"] = " ".join(rest)
        else:
            raise UsageError("expects a prompt (optionally preceded by a role).")
        if "tier" in flags:
            payload["model_tier"] = flags["tier"]
        if "attach" in flags:
            payload["file_references"] = flags["attach"]
        if "standalone" in flags:
            payload["child"] = False
        if "no_wait" in flags:
            payload["wait"] = False
        if "eval" in flags:
            payload["conduct"] = True
        if "project" in flags:
            payload["project"] = flags["project"]
        if "base" in flags:
            payload["base"] = flags["base"]
        if "pins" in flags:
            payload["pins"] = _json_flag("pins", flags["pins"])
        payload.update({k: flags[k] for k in OVERRIDE_FIELDS if k in flags})
        return validate(schema, payload)

    def _parse_resume(flags: dict[str, Any], rest: list[str]) -> BaseModel | None:
        if rest or "outcome" not in flags:
            raise UsageError(
                "--resume expects `<request> --outcome approve|deny|escalate|mock "
                "[--message TEXT] [--result TEXT [--error]]`."
            )
        payload: dict[str, Any] = {"resume": flags["resume"], "outcome": flags["outcome"]}
        if "message" in flags:
            payload["message"] = flags["message"]
        if "result" in flags:
            payload["result"] = flags["result"]
        if "error" in flags:
            payload["result_is_error"] = True
        return validate(schema, payload)

    return parse


def _enum_values(annotation: Any) -> set[str]:
    members = [a for a in get_args(annotation) or (annotation,) if isinstance(a, type) and issubclass(a, Enum)]
    return {m.value for e in members for m in e}


def host_argv(model: type[BaseModel] | None) -> ParseFn:
    """`host_cmd [--cwd DIR] [--timeout SECONDS] <command...>` — one gated host command.

    Flags stop at the first positional; the rest is the command. One positional
    is a host shell line passed verbatim (pipes run on the host). Several are an
    exact argv, quoted so `sh -c 'a && b'` and `git merge --ff-only X` survive.
    """
    schema = _required(model)

    def parse(args: list[str]) -> BaseModel | None:
        split = 0
        while split < len(args) and args[split].startswith("--"):
            split += 1 if "=" in args[split] else 2
        flags, _ = flags_of(args[:split], values={"cwd", "timeout"})
        rest = args[split:]
        if not rest:
            raise UsageError("expects a command to run on the host.")
        command = rest[0] if len(rest) == 1 else shlex.join(rest)
        payload: dict[str, Any] = {"commands": [command]}
        if "cwd" in flags:
            payload["working_directory"] = flags["cwd"]
        if "timeout" in flags:
            payload["timeout"] = flags["timeout"]
        return validate(schema, payload)

    return parse


def _json_flag(name: str, raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise UsageError(f"`--{name}` expects a JSON value ({e}).") from e


def infer_parser(model: type[BaseModel] | None) -> ParseFn:
    """Derive a parser from a schema the registry has never seen.

    Two shapes cover nearly every unregistered tool: a lone ``list[str]`` field
    takes argv verbatim, and a lone ``str`` field takes the joined tail. Anything
    else falls back to a single JSON object argument, which is always available
    as an escape hatch.
    """
    if model is None:
        return no_args(None)
    fields = model.model_fields
    if len(fields) == 1:
        (name, field), = fields.items()
        if field.annotation == list[str]:
            return passthrough(name)(model)
        if field.annotation is str:
            return joined_tail(name, required=field.is_required())(model)
    return json_arg(model)


def parser_for(builder: ParserBuilder | None, model: type[BaseModel] | None) -> ParseFn:
    return (builder or infer_parser)(model)


def usage_for(command_id: str, model: type[BaseModel] | None) -> str:
    """A one-line usage string inferred from *model*.

    A tool declaring ``argv`` must declare its ``usage`` too (enforced by
    tests): a schema-derived guess would describe the JSON fallback for
    commands that don't accept JSON.
    """
    if model is None:
        return command_id
    fields = model.model_fields
    if len(fields) == 1:
        ((field_name, field),) = fields.items()
        if field.annotation == list[str] or field.annotation is str:
            return f"{command_id} <{field_name}...>"
    return f"{command_id} '{{<json object>}}'"
