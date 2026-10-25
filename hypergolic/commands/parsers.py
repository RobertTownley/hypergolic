"""Turning a shell's argv into a command's validated input model.

A command declares an ``input_schema``; the shim delivers whatever tokens the
sandbox shell parsed. A ``ParseFn`` bridges the two, and the broker runs it
before approval so a policy and a handler can never disagree about what an argv
meant.

``parse`` receives the argv *tail* as a token list, already split by the shell.
Re-joining it to re-split would throw away quoting the shell established:
``["-m", "a; b"]`` and ``["-m", "a", ";", "b"]`` must stay distinguishable, and
argv-as-list is what makes metacharacter smuggling into a host handler
impossible.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Iterable

from pydantic import BaseModel

ParseFn = Callable[[list[str]], BaseModel | None]

#: Builds a command's parser from the tool's input model. Declared
#: as builders rather than closures over a model so the registry can bind them
#: to per-session tools (dispatch targets, skill enums) built at turn time.
ParserBuilder = Callable[[type[BaseModel] | None], ParseFn]


class NoInput(BaseModel):
    """Stand-in input for a command whose tool takes none.

    A schema-less tool needs *something* to return, because a parser that yields
    no input at all is indistinguishable from one that failed. ``invoke_tool``
    ignores it (the tool's ``run`` takes only a context) and it dumps to ``{}``
    for approval.
    """


class UsageError(Exception):
    """A command matched but its arguments were wrong.

    Distinct from a ``parse`` returning ``None`` (a decline): this reports a
    self-correcting message back to the model instead of falling through.
    """


def no_args(model: type[BaseModel] | None) -> ParseFn:
    """Parser for a command that takes nothing."""

    def _parse(args: list[str]) -> BaseModel | None:
        if args:
            raise UsageError(f"takes no arguments, got {args!r}.")
        return model() if model is not None else NoInput()

    return _parse


def json_arg(model: type[BaseModel]) -> ParseFn:
    """Parser accepting a single JSON object argument matching *model*.

    The fallback for genuinely structured inputs (nested objects, dynamic
    schemas) where flags would be worse than JSON.
    """

    def _parse(args: list[str]) -> BaseModel | None:
        return validate(model, _json_payload(args))

    return _parse


def validate(model: type[BaseModel], payload: dict[str, Any]) -> BaseModel:
    try:
        return model.model_validate(payload)
    except Exception as e:
        raise UsageError(f"invalid arguments: {e}") from e


def _json_payload(args: list[str]) -> dict[str, Any]:
    if not args:
        return {}
    if len(args) > 1:
        raise UsageError(
            f"expects a single JSON object argument, got {len(args)} tokens — "
            "quote the JSON as one argument, or pass `@-` and send it as a "
            "quoted heredoc (cmd @- <<'EOF' ... EOF)."
        )
    try:
        payload = json.loads(args[0])
    except json.JSONDecodeError as e:
        raise UsageError(
            f"expects one JSON object argument; couldn't parse it ({e})."
        ) from e
    if not isinstance(payload, dict):
        raise UsageError(f"expects a JSON object, got {type(payload).__name__}.")
    return payload


def take_flags(
    args: list[str],
    *,
    bools: Iterable[str] = (),
    values: Iterable[str] = (),
    multi: Iterable[str] = (),
    open_ended: bool = False,
    normalize: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """Split ``--flag`` / ``--flag value`` tokens from positionals.

    Supports ``--flag=value``. Names in *multi* accumulate into a list, so
    repeating a flag (``--attach a --attach b``) is how list fields are filled.
    Dashes in flag names are normalized to underscores so they land on pydantic
    fields directly.

    *open_ended* accepts any flag: it takes the next token as its value unless
    that token is itself a flag, and is ``True`` otherwise. *normalize* off keeps
    the flag spelling as typed.
    """
    bool_set, value_set, multi_set = set(bools), set(values), set(multi)
    flags: dict[str, Any] = {}
    rest: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        if tok == "--":
            # Everything after `--` is a positional, so prose that happens to
            # start with dashes stays expressible.
            rest.extend(args[i + 1 :])
            break
        if not tok.startswith("--"):
            rest.append(tok)
            i += 1
            continue
        key, eq, inline = tok[2:].partition("=")
        norm = key.replace("-", "_") if normalize else key
        if norm in bool_set and not eq:
            flags[norm] = True
        elif norm in value_set or norm in multi_set:
            if eq:
                value = inline
            elif i + 1 < len(args):
                i += 1
                value = args[i]
            else:
                raise UsageError(f"`--{key}` needs a value.")
            if norm in multi_set:
                flags.setdefault(norm, []).append(value)
            else:
                flags[norm] = value
        elif open_ended:
            if eq:
                flags[norm] = inline
            elif i + 1 < len(args) and not args[i + 1].startswith("--"):
                i += 1
                flags[norm] = args[i]
            else:
                flags[norm] = True
        else:
            raise UsageError(f"unknown flag `--{key}`.")
        i += 1
    return flags, rest
