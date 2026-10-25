import logging
from pathlib import Path
from anthropic.types import Message, MessageParam, TextBlockParam

from hypergolic.config.settings import PROMPTS_DIR
from hypergolic.enums import ModelTier
from hypergolic.messages.block_guards import (
    is_text_block,
    is_tool_result_block,
    is_tool_use_block,
    iter_content_blocks,
)
from hypergolic.providers import client_for_tier, tier_to_model_id

logger = logging.getLogger(__name__)

TOOL_RESULT_MAX_CHARS = 2000
# Tool inputs carry whole file bodies (heredoc writes), so they need the same
# cap as results — the transcript is the full conversation and would otherwise
# grow past the context window of the model asked to summarize it.
TOOL_INPUT_MAX_CHARS = 2000
SUMMARIZE_PROMPT_PATH = PROMPTS_DIR / "summarize_prompt.md"
# Thinking is on by default and spends this same budget, so the summary needs
# headroom well beyond the text it has to emit.
SUMMARY_MAX_TOKENS = 12288


def _truncate_tool_result(text: str, max_chars: int = TOOL_RESULT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\u2026 (content truncated for brevity)"


def build_conversation_transcript(messages: list[MessageParam]) -> list[TextBlockParam]:
    blocks: list[TextBlockParam] = []

    for msg in messages:
        role = msg.get("role", "user")
        raw_content = msg.get("content", [])

        if isinstance(raw_content, str):
            if raw_content.strip():
                blocks.append({"type": "text", "text": f"[{role}]: {raw_content}"})
            continue

        text_parts: list[str] = []
        for block in iter_content_blocks(raw_content):
            if is_text_block(block):
                text = block.get("text", "")
                if text.strip():
                    text_parts.append(text)
            elif is_tool_use_block(block):
                name = block.get("name", "unknown")
                inp = _truncate_tool_result(
                    str(block.get("input", {})), TOOL_INPUT_MAX_CHARS
                )
                text_parts.append(f"[Tool call: {name}({inp})]")
            elif is_tool_result_block(block):
                tool_content = block.get("content", [])
                is_error = block.get("is_error", False)
                prefix = "Tool error" if is_error else "Tool result"
                if isinstance(tool_content, str):
                    text_parts.append(f"[{prefix}: {_truncate_tool_result(tool_content)}]")
                elif isinstance(tool_content, list):
                    for sub in tool_content:
                        if is_text_block(sub):
                            text_parts.append(
                                f"[{prefix}: {_truncate_tool_result(sub.get('text', ''))}]"
                            )

        if text_parts:
            combined = "\n".join(text_parts)
            blocks.append({"type": "text", "text": f"[{role}]: {combined}"})

    return blocks


def _build_system_prompt(prompt_path: Path) -> list[TextBlockParam]:
    blocks: list[TextBlockParam] = []

    if prompt_path.exists():
        blocks.append({"type": "text", "text": prompt_path.read_text()})

    return blocks


def extract_summary_text(response: Message) -> str:
    summary_text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            summary_text += getattr(block, "text", "")

    if not summary_text.strip():
        # Report the response shape: a thinking-only response that stopped on
        # max_tokens means the output budget was spent before any text, which
        # is a different fix than a provider returning nothing at all.
        block_types = [getattr(b, "type", "?") for b in response.content]
        raise ValueError(
            "Summarization model returned empty response "
            f"(model={response.model}, stop_reason={response.stop_reason}, "
            f"blocks={block_types}, output_tokens="
            f"{response.usage.output_tokens if response.usage else None})."
        )

    return summary_text


async def call_summarization_model(
    tier: ModelTier,
    messages: list[MessageParam],
    prompt_path: Path = SUMMARIZE_PROMPT_PATH,
    closing: str = "Please summarize this conversation now.",
    max_tokens: int = SUMMARY_MAX_TOKENS,
) -> Message:
    client = client_for_tier(tier)
    model_id = tier_to_model_id(tier)
    system_prompt = _build_system_prompt(prompt_path)

    transcript_blocks = build_conversation_transcript(messages)
    if not transcript_blocks:
        raise ValueError("No message content to summarize after flattening.")

    transcript_blocks.append({"type": "text", "text": closing})

    summarize_messages: list[MessageParam] = [
        {"role": "user", "content": transcript_blocks},
    ]

    response = await client.messages.create(
        max_tokens=max_tokens,
        model=model_id,
        messages=summarize_messages,
        system=system_prompt,
    )

    extract_summary_text(response)
    return response
