"""MCP as one shim rather than a tool list.

An MCP server's tools are runtime data, discovered by connecting; declaring them
as tool schemas rewrites the prompt prefix whenever a server is enabled (~20k
cache-write tokens). Instead the whole surface is one command whose subcommands
read that data at call time. Arguments are validated server-side against the
server-held schema, and ``exec`` approval is the harness' own mcp_approval_policy.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import ValidationError

from hypergolic.commands.parsers import UsageError, take_flags
from hypergolic.harness.primitives.results import InputSchema
from hypergolic.mcptools.json_schema import declared_types

ACTIONS = ("list", "activate", "deactivate", "schema", "exec")

#: Reading what exists is safe; connecting is not (it reaches a remote server and
#: may open a browser for OAuth), and ``exec`` defers to the harness' policy.
_READ_ONLY = {"list", "schema"}


class McpInput(InputSchema):
    action: Literal["list", "activate", "deactivate", "schema", "exec"]
    server: str | None = None
    tool: str | None = None
    arguments: dict[str, Any] = {}
    #: Keys whose values are unparsed flag text, for the schema to type.
    literal: list[str] = []


class McpOutput(InputSchema):
    servers: list[dict] = []
    input_schema: dict = {}
    content: list[dict] = []


def _typed_value(raw: str, prop_schema: Any) -> Any:
    """A flag's text as the type the property declares; JSON arbitrates when it
    declares none, or when text is only one of the types it accepts.
    """
    if {t for t in declared_types(prop_schema) if t != "null"} == {"string"}:
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _json_object(token: str) -> Any:
    try:
        return json.loads(token)
    except json.JSONDecodeError:
        return token


def _arguments(tokens: list[str]) -> tuple[dict[str, Any], list[str]]:
    """The parsed arguments, plus the keys whose values are still raw flag text.

    Typing needs the schema, which the parser does not have, so it records what
    it read verbatim and leaves the decision to ``_align_to_schema``.
    """
    flags, rest = take_flags(tokens, open_ended=True, normalize=False)
    arguments: dict[str, Any] = {}
    for token in rest:
        # The escape hatch for a schema flags cannot express.
        payload = _json_object(token)
        if not isinstance(payload, dict):
            raise UsageError(
                f"expected `--flag=value` or a JSON object, got {token!r}."
            )
        arguments.update(payload)
    arguments.update(flags)
    return arguments, [key for key, value in flags.items() if isinstance(value, str)]


def _align_to_schema(
    arguments: dict[str, Any], schema: dict, literal: list[str] | None = None
) -> dict[str, Any]:
    """Spell and type the arguments the way the schema the server published does.

    A flag cannot know whether the field behind it is ``chart_id`` or
    ``issue-tracker``, nor whether its digits are a number or a timestamp string,
    and guessing either at parse time failed silently — a mangled key made an
    enable a no-op, a mangled type made a threaded reply land in the channel.
    The schema is authoritative for both: a key absent from it is retried in its
    other spelling, and text the parser read verbatim becomes the type declared
    for it. Values from the JSON escape hatch are already typed by the caller.
    """
    properties = schema.get("properties") or {}
    verbatim = set(arguments) if literal is None else set(literal)
    aligned: dict[str, Any] = {}
    for key, value in arguments.items():
        typeable = key in verbatim and isinstance(value, str)
        if key not in properties:
            for candidate in (key.replace("-", "_"), key.replace("_", "-")):
                if candidate in properties and candidate not in aligned:
                    key = candidate
                    break
        aligned[key] = _typed_value(value, properties.get(key)) if typeable else value
    return aligned



def parse_mcp(args: list[str]) -> McpInput:
    if not args:
        raise UsageError(f"expects a subcommand ({', '.join(ACTIONS)}).")
    action, *rest = args
    if action not in ACTIONS:
        raise UsageError(f"unknown subcommand {action!r}; expected one of {', '.join(ACTIONS)}.")

    payload: dict[str, Any] = {"action": action}
    if action == "list":
        if rest:
            raise UsageError(f"`list` takes no arguments, got {rest!r}.")
    elif action in ("activate", "deactivate"):
        if len(rest) != 1:
            raise UsageError(f"`{action}` expects one server name.")
        payload["server"] = rest[0]
    elif action == "schema":
        if len(rest) != 2:
            raise UsageError("`schema` expects a server and a tool name.")
        payload["server"], payload["tool"] = rest
    else:
        if len(rest) < 2:
            raise UsageError("`exec` expects a server, a tool name, then arguments.")
        payload["server"], payload["tool"] = rest[0], rest[1]
        payload["arguments"], payload["literal"] = _arguments(rest[2:])
    try:
        return McpInput.model_validate(payload)
    except ValidationError as exc:
        raise UsageError(f"invalid arguments: {exc}") from exc
