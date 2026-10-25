"""Ranking a session's commands against a description of a task.

Discovery starts from the words the agent already has — what it is trying to do —
because the name of the command it hasn't found yet is exactly what it is missing.
So the query is prose, matching is per-word, and every text a declaration carries
is searchable.

A command scores once per distinct query word, at the weight of the strongest
field that word appears in, and the total is multiplied by how many of the words
it answered. Both halves are load-bearing. The weight spread keeps a declared tag
above words that merely occur in a long prompt body, or every skill with a big
SKILL.md answers every question. The coverage multiplier keeps a command that
answers most of the query above one that shares a single generic word with it —
without it, `harness-tools` beats `history` on "how the harness gets used",
because ids like `harness-*` donate a word every harness question contains.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hypergolic.harness.primitives.tool import Tool

#: Words that carry no signal in a task description. Small on purpose — a long
#: list starts eating query terms that happen to be command vocabulary.
_STOPWORDS = frozenset(
    """a an and any are as at be by can do does for from get give has have how i if
    in into is it its me my not of on or so that the their then there this to up use
    used using want was what when where which who why will with without you your""".split()
)

_SUFFIXES = ("ing", "ers", "er", "ies", "es", "ed", "s")

#: Shortest token that may match by prefix. Below this, "co" would match
#: "commit", "container" and "config" alike.
_MIN_PREFIX = 4

#: How much longer than a term a word may be and still count as the same word.
#: Prefix matching exists to absorb inflection the stemmer missed, not to glue
#: distinct words together: "work" must not match "workflow", or "delegate work"
#: comes back with the workflow commands as confident answers.
_MAX_PREFIX_GAP = 3


def _words(text: str) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        elif current:
            out.append("".join(current))
            current = []
    if current:
        out.append("".join(current))
    return out


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def terms(text: str) -> list[str]:
    """The query reduced to distinct, stemmed, meaning-bearing words."""
    seen: set[str] = set()
    out: list[str] = []
    for word in _words(text):
        if len(word) < 2 or word in _STOPWORDS:
            continue
        stem = _stem(word)
        if stem not in seen:
            seen.add(stem)
            out.append(stem)
    return out


def stems(*texts: str) -> set[str]:
    return {_stem(word) for text in texts for word in _words(text)}


def _weighted_fields(command: Tool) -> list[tuple[int, set[str]]]:
    """Searchable text by how directly it declares purpose."""
    examples = " ".join(f"{e.command} {e.note}" for e in command.examples)
    return [
        (20, stems(command.id, *command.tags)),
        (8, stems(command.name)),
        (6, stems(command.description)),
        (3, stems(command.usage, examples)),
        (1, stems(command.guidance)),
    ]


def matches_word(term: str, field: set[str]) -> bool:
    if term in field:
        return True
    if len(term) < _MIN_PREFIX:
        return False
    return any(
        len(word) >= _MIN_PREFIX
        and abs(len(word) - len(term)) <= _MAX_PREFIX_GAP
        and (word.startswith(term) or term.startswith(word))
        for word in field
    )


#: The score below which a match is one incidental word, not an answer: a single
#: mid-weight hit. "Design, write, and refine Hypergolic roles" matches "look at a
#: design mock" that way, and presenting that as *the* answer is worse than saying
#: nothing fits — the agent stops looking and reads the wrong README.
STRONG_SCORE = 12


@dataclass(frozen=True)
class Match:
    command: Tool
    score: int
    hits: tuple[str, ...]

    @property
    def strong(self) -> bool:
        return self.score >= STRONG_SCORE


def score(command: Tool, query_terms: Iterable[str]) -> Match:
    fields = _weighted_fields(command)
    total = 0
    hits: list[str] = []
    for term in query_terms:
        best = max((weight for weight, field in fields if matches_word(term, field)), default=0)
        if best:
            total += best
            hits.append(term)
    return Match(command=command, score=total * len(hits), hits=tuple(hits))


def search(commands: Iterable[Tool], query: str, limit: int = 10) -> list[Match]:
    """Commands answering *query*, best first. Empty when nothing matched."""
    query_terms = terms(query)
    if not query_terms:
        return []
    found = [match for match in (score(c, query_terms) for c in commands) if match.score]
    if not found:
        return []
    # A *relative* floor, because a long guidance body mentions almost any word
    # eventually: once something answers directly, an incidental mention is noise.
    # Relative rather than absolute so a weak-but-only answer still gets through —
    # the alternative is a miss, and a miss makes the agent believe nothing exists.
    floor = max(m.score for m in found) // 4
    found = [m for m in found if m.score >= floor]
    found.sort(key=lambda m: (-m.score, -len(m.hits), m.command.id))
    return found[:limit]
