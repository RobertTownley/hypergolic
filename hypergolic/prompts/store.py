
from hypergolic.sessions import session_rows
from hypergolic.prompts.blocks import PromptBlock


def load_prompt_blocks(session_id: str) -> list[PromptBlock] | None:
    row = session_rows.fetch(session_id)
    stored = row.prompt_blocks if row is not None else None
    if not stored:
        return None
    return [PromptBlock(source=b["source"], text=b["text"]) for b in stored]


def save_prompt_blocks(session_id: str, blocks: list[PromptBlock]) -> None:
    payload = [{"source": b.source, "text": b.text} for b in blocks]
    session_rows.update(session_id, prompt_blocks=payload)
