from __future__ import annotations

from dataclasses import dataclass

from hypergolic.commands.search import matches_word, stems


@dataclass(frozen=True)
class Section:
    title: str
    start: int
    end: int


def _spans(lines: list[str]) -> list[Section]:
    heads = [i for i, line in enumerate(lines) if line.startswith("#")]
    ends = heads[1:] + [len(lines)]
    return [Section(lines[h].lstrip("# ").strip(), h + 1, e) for h, e in zip(heads, ends)]


def best_section(text: str, hits: tuple[str, ...]) -> Section | None:
    lines = text.splitlines()
    spans = _spans(lines)
    if len(spans) < 2:
        return None
    title = stems(spans[0].title)
    hits = tuple(t for t in hits if not matches_word(t, title))
    if not hits:
        return None

    def score(span: Section) -> int:
        words = stems(*lines[span.start - 1 : span.end])
        return sum(matches_word(t, words) for t in hits)

    best = max(spans, key=score)
    return best if score(best) else None
