from typing import cast

from hypergolic.messages import message_rows

PREVIEW_MAX_CHARS = 2000


def extract_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                typed_block = cast(dict[str, object], block)
                if typed_block.get("type") == "text":
                    text = typed_block.get("text", "")
                    if isinstance(text, str):
                        parts.append(text)
        return "".join(parts)
    return ""


def _user_contents(session_id: str) -> list[object]:
    return [
        r.content for r in message_rows.for_session(session_id)
        if r.role == "user" and not r.truncated
    ]


def count_user_text_chars(session_id: str) -> int:
    return sum(len(extract_text(c)) for c in _user_contents(session_id))


def get_user_text_preview(session_id: str) -> str:
    parts = [extract_text(c) for c in _user_contents(session_id)]
    return "\n".join(p for p in parts if p)[:PREVIEW_MAX_CHARS]
