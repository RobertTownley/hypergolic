from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from anthropic.types import TextBlockParam


class InputSchema(BaseModel):
    pass


class ToolResult(BaseModel):
    """The result of a tool invocation.

    ``content`` is a list of Anthropic content blocks. ``is_error`` flags the
    result as an error to the model.

    ``meta`` is structured detail for the UI alone — it is stored on the
    tool_result block and stripped before the conversation is sent to the
    provider, so a tool can hand the transcript facts (which workflow state
    was entered, say) without the UI parsing them back out of the prose.
    """

    model_config = ConfigDict(extra="forbid")

    content: list[dict] = Field(default_factory=list)
    is_error: bool = False
    meta: dict | None = None

    @classmethod
    def text(cls, text: str, *, is_error: bool = False, meta: dict | None = None) -> "ToolResult":
        """Build a ToolResult containing a single text block."""
        return cls(content=[{"type": "text", "text": text}], is_error=is_error, meta=meta)

    def append_text(self, text: str) -> "ToolResult":
        """Return a new ToolResult with an additional text block appended."""
        return ToolResult(
            content=[*self.content, {"type": "text", "text": text}],
            is_error=self.is_error,
            meta=self.meta,
        )

    def iter_text_blocks(self) -> Iterator[TextBlockParam]:
        """Yield only the TextBlockParam entries from content, properly typed."""
        for block in self.content:
            if isinstance(block, dict) and block.get("type") == "text":
                yield cast("TextBlockParam", block)

    def total_text_chars(self) -> int:
        """Sum the character count of all text blocks."""
        return sum(len(b["text"]) for b in self.iter_text_blocks())

    def first_text(self) -> str:
        """Text of the first content block. Raises if it is not a text block."""
        if not self.content:
            raise IndexError("ToolResult has no content blocks")
        block = self.content[0]
        if not (isinstance(block, dict) and block.get("type") == "text"):
            actual = block.get("type") if isinstance(block, dict) else type(block).__name__
            raise TypeError(f"Expected text block, got {actual!r}")
        return cast("TextBlockParam", block)["text"]


class CommandExample(BaseModel):
    """A concrete invocation, rendered into ``--help`` and the README.

    Chaining and piping examples are the point: they are how an agent learns a
    command composes with the rest of the shell.
    """

    command: str
    note: str = ""


class CommandResult(BaseModel):
    """What a command handler returns, and what the broker streams back.

    Structured rather than stringly-typed: ``exit_code`` is what the surrounding
    shell branches on, and ``data`` (validated against ``output_schema``) is what
    lets the UI render success versus error structurally.
    """

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    data: Any = None

    @property
    def is_error(self) -> bool:
        return self.exit_code != 0

    @classmethod
    def ok(cls, stdout: str = "", *, data: Any = None) -> "CommandResult":
        return cls(stdout=stdout, data=data)

    @classmethod
    def fail(cls, stderr: str, *, exit_code: int = 1) -> "CommandResult":
        return cls(stderr=stderr, exit_code=exit_code)

    @classmethod
    def from_tool_result(cls, result: "ToolResult") -> "CommandResult":
        """Adapt a handler that answers in the model-facing shape.

        Handlers predate ``CommandResult`` and many still return a
        :class:`ToolResult`; a shell caller needs its text on the right stream
        with an exit code it can branch on, not a pydantic repr.
        """
        text = "\n".join(block["text"] for block in result.iter_text_blocks())
        if result.is_error:
            return cls(stderr=text, exit_code=1)
        return cls(stdout=text)
