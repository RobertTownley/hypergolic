from dataclasses import dataclass

from anthropic.types import TextBlockParam


@dataclass
class PromptBlock:
    source: str
    text: str

    def to_text_block(self) -> TextBlockParam:
        return {"type": "text", "text": self.text}


def to_text_blocks(blocks: list[PromptBlock]) -> list[TextBlockParam]:
    return [block.to_text_block() for block in blocks]
