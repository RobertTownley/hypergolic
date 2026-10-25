"""Test helpers for extracting content from tool outputs and messages.

The Anthropic SDK types tool-result content as a wide union
(`TextBlockParam | ImageBlockParam | SearchResultBlockParam |
 DocumentBlockParam | ToolReferenceBlockParam`). Most of our tools return
text blocks exclusively, so these helpers do the narrowing in one place
and let tests assert against plain strings.
"""

from typing import Any

from hypergolic.messages.block_guards import is_text_block


def text_at(content: Any, index: int = 0) -> str:
    """Return the `text` of the block at `index`, asserting it's a text block."""
    block = content[index]
    assert is_text_block(block), f"expected text block at index {index}, got {block!r}"
    return block["text"]


def first_text(content: Any) -> str:
    """Shortcut for `text_at(content, 0)`."""
    return text_at(content, 0)


def all_texts(content: Any) -> list[str]:
    """The `text` of every text block in `content`, skipping non-text blocks."""
    return [block["text"] for block in content if is_text_block(block)]
