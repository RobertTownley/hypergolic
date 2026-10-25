from __future__ import annotations

import inspect
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

from pydantic import BaseModel, Field, model_validator

from hypergolic.harness.primitives.approval import (
    ApprovalDecision,
    ApprovalPolicy,
    always,
)
from hypergolic.harness.primitives.results import CommandExample
from hypergolic.messages.types import BroadcastFn
from hypergolic.schemas import Session
from hypergolic.tools.approval_view import ApprovalView


@dataclass
class ToolContext:
    session: Session
    broadcast: BroadcastFn
    tool_id: str
    #: Container cwd of the shim invocation (advisory, from the broker), or
    #: None when the tool was called outside a sandbox exec. Lets repo-aware
    #: tools like `git` act on the repo the agent is standing in.
    invocation_cwd: str | None = None
    tool_use_id: str | None = None

    def sandbox_id(self, qualifier: str | None = None) -> str:
        """Return the sandbox key for this tool invocation.

        Pass a qualifier to run multiple sandboxes from one tool:
            ctx.sandbox_id("uv")  ->  "python_lab_uv"
        Without a qualifier, the tool has a single sandbox keyed by tool_id.
        """
        if qualifier:
            return f"{self.tool_id}_{qualifier}"
        return self.tool_id


# --- Tool: one declarative primitive ----------------------------------------
#
# A ``Tool`` carries everything an agent needs to *find, understand, and
# invoke* a capability, and everything the harness needs to authorize and route
# it. It is what materializes into ``/tools``: a shim on ``PATH``, a generated
# README, and one line in the system prompt's relevance index.
#
# ``Skill``, ``Role``, ``Workflow`` and friends declare *bundles* of tools.

HOST = "host"
SANDBOX = "sandbox"
_CONTAINER_PREFIX = "container:"


def container_domain(container_id: str) -> str:
    return f"{_CONTAINER_PREFIX}{container_id}"


def domain_container(domain: str) -> str | None:
    """The container a ``container:<id>`` domain names, else ``None``."""
    if domain.startswith(_CONTAINER_PREFIX):
        return domain[len(_CONTAINER_PREFIX):] or None
    return None


def _normalize_tags(tags: Iterable[Any]) -> list[str]:
    """Lowercase, hyphenate, dedupe — a tag is matched, never displayed as typed."""
    seen: dict[str, None] = {}
    for tag in tags:
        cleaned = "-".join(str(tag).lower().split())
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)


class Tool(BaseModel):
    """One invocable (or purely advisory) capability.

    A tool with a ``run`` gets a shim in ``/tools/bin`` and is invocable; one
    without gets only a ``/tools/<id>/README.md``, which is how a prompt-only
    skill becomes documentation without needing a separate mechanism.
    """

    id: str
    name: str
    #: WHEN to reach for this. Emitted as one static line in the system prompt's
    #: relevance index — ``--help`` answers *how* but never answers *when*.
    description: str
    usage: str = ""
    #: Long-form guidance, rendered into the README. Where a SKILL.md prompt goes.
    guidance: str = ""
    #: Task vocabulary `apropos` searches: the words a user or agent would reach
    #: for before knowing this command exists. Never sent over the wire, so tag
    #: for recall — synonyms, the domain noun, the failure that leads here.
    tags: list[str] = Field(default_factory=list)
    input_schema: type[BaseModel] | None = None
    output_schema: type[BaseModel] | None = None
    examples: list[CommandExample] = Field(default_factory=list)
    domain: str = HOST
    #: Read this back through `approval_policy`, which resolves the string form.
    approval: ApprovalPolicy | ApprovalDecision = Field(
        default_factory=lambda: always("ALLOW")
    )
    run: Callable | None = None
    eval_behavior: Callable | None = None
    #: ``async (input, ctx) -> ValidationResult`` run before approval; INVALID fails the call unprompted.
    validate_tool_call: Callable | None = None
    #: Argv -> ``input_schema``. Left unset, the registry derives one.
    parse: Callable[[list[str]], BaseModel | None] | None = None
    #: Builds ``parse`` from ``input_schema`` at registration, so a per-session
    #: schema (dispatch targets, child ids) keeps the declared argv shape.
    argv: Callable[[type[BaseModel] | None], Callable[[list[str]], BaseModel | None]] | None = None
    timeout: int = 120
    requires_worktree: bool = False
    #: Which skill / role / workflow / project / MCP server contributed this.
    origin: str = "app"
    approval_view: ApprovalView | None = None

    model_config = {"arbitrary_types_allowed": True}

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        """Accept the two shorthands every declaration in the wild uses.

        A string ``approval`` becomes the equivalent total policy, so a command
        whose posture doesn't depend on its arguments doesn't have to spell one
        out. And a multi-paragraph ``description`` splits at the first newline:
        the index line in /tools/index.md and apropos output has to be one line, while everything
        after it is exactly what the README's guidance section is for.
        """
        if not isinstance(data, dict):
            return data
        patch: dict[str, Any] = {}
        approval = data.get("approval")
        if isinstance(approval, str):
            patch["approval"] = always(cast(ApprovalDecision, approval))
        tags = data.get("tags")
        if isinstance(tags, (list, tuple)):
            patch["tags"] = _normalize_tags(tags)
        description = data.get("description")
        if isinstance(description, str) and "\n" in description and not data.get("guidance"):
            head, _, tail = description.strip().partition("\n")
            patch["description"] = head.strip()
            patch["guidance"] = tail.strip()
        return {**data, **patch} if patch else data

    @model_validator(mode="after")
    def _validate(self) -> "Tool":
        if self.run is not None and not inspect.iscoroutinefunction(self.run):
            fn_name = getattr(self.run, "__name__", "<unknown>")
            raise ValueError(
                f"Tool '{self.id}' run function must be async. "
                f"Change 'def {fn_name}(...)' to 'async def {fn_name}(...)'."
            )
        if self.validate_tool_call is not None and not inspect.iscoroutinefunction(self.validate_tool_call):
            raise ValueError(f"Tool '{self.id}' validate_tool_call function must be async.")
        if self.domain not in (HOST, SANDBOX) and domain_container(self.domain) is None:
            raise ValueError(
                f"Tool '{self.id}' has invalid domain {self.domain!r}; "
                f"expected 'host', 'sandbox', or 'container:<id>'."
            )
        return self

    @property
    def invocable(self) -> bool:
        return self.run is not None

    @property
    def approval_policy(self) -> ApprovalPolicy:
        """`approval` with the string shorthand resolved to a real policy."""
        if callable(self.approval):
            return self.approval
        return always(self.approval)

    def source_file(self) -> Path | None:
        """Host path of the module declaring this command's behaviour.

        ``/tools/<id>/source`` symlinks here rather than copying, so what the
        agent reads cannot drift from what will run.
        """
        target = self.run or self.approval_policy
        try:
            path = inspect.getsourcefile(target)  # type: ignore[arg-type]
        except TypeError:
            return None
        return Path(path) if path else None


class ToolRegistryMixin:
    tools: list[Tool]

    def register_tool(self, tool: Tool) -> None:
        self.tools.append(tool)

    def register_tools(self, tools: list[Tool]) -> None:
        self.tools.extend(tools)
