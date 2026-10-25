"""`apropos` — find the command for a task from the words describing the task.

The system prompt names no commands, so the catalog (tags, guidance,
examples) is only reachable by pulling it, and `--help` cannot help an agent that
does not yet know which name to ask about. This is the name a Unix-literate agent
already reaches for, pointed at the harness's own command set.
"""

from __future__ import annotations

from pydantic import Field

from hypergolic.commands.search import Match, search, terms
from hypergolic.commands.sections import best_section
from hypergolic.commands.shared_index import SHARED_ORIGIN, shared_commands
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import CommandExample, CommandResult, InputSchema
from hypergolic.harness.primitives.tool import HOST, Tool, ToolContext
from hypergolic.commands.registry import session_commands
from hypergolic.commands.argv import positional
from hypergolic.mcptools.discovery import MCP_SERVER_ORIGIN, server_commands


class AproposInput(InputSchema):
    query: str = Field(
        description="What you are trying to do, in your own words. Prose, not a name."
    )
    limit: int = Field(default=5, description="Most matches to print.")


class AproposOutput(InputSchema):
    query: str = ""
    matched: list[str] = []
    total: int = 0


_BRIEF = 120


def _brief(text: str) -> str:
    first = text.split(". ")[0].strip()
    return first if len(first) <= _BRIEF else first[: _BRIEF - 1] + "\u2026"


def _pointer(match: Match) -> str:
    command = match.command
    if not command.usage.startswith("cat "):
        return command.usage
    section = best_section(command.guidance, match.hits)
    if section is None:
        return command.usage
    return f"sed -n {section.start},{section.end}p /shared/{command.id}  (\u00a7 {section.title})"


def _entry(match: Match) -> str:
    command = match.command
    if command.origin == MCP_SERVER_ORIGIN:
        return f"{command.id} (MCP server) \u2014 {_brief(command.description)}  \u2192  {command.usage}"
    if command.origin == SHARED_ORIGIN:
        return f"{command.id} \u2014 {_brief(command.description)}  \u2192  {_pointer(match)}"
    marker = "" if command.invocable else " (docs only)"
    return f"{command.id}{marker} \u2014 {_brief(command.description)}"


def _retry(query: str) -> str:
    word = max(terms(query), key=len, default="<word>")
    return (
        "Retry with 1-3 other words, `cat /tools/index.md` for every command, or "
        f"`compgen -c | grep -i {word}` for installed programs. Definitions: "
        "/tools/<name>/source; skills in /hypergolic/contrib/prompts/skills and /harness/skills."
    )


def _next_steps(matches: list[Match]) -> list[str]:
    steps = []
    if any(m.command.origin not in (SHARED_ORIGIN, MCP_SERVER_ORIGIN) for m in matches):
        steps.append("`<name> --help` for usage.")
    if any(m.command.origin == SHARED_ORIGIN and not m.command.usage.startswith("cat ") for m in matches):
        steps.append("/shared scripts are unreviewed: read before running.")
    return steps


def _render(query: str, matches: list[Match]) -> str:
    strong = [m for m in matches if m.strong]
    weak = [m for m in matches if not m.strong]
    if strong:
        tail = ["Weaker: " + ", ".join(m.command.id for m in weak)] if weak else []
        return "\n".join([*(f"- {_entry(m)}" for m in strong), *tail, *_next_steps(strong)])
    if weak:
        return "\n".join(
            [f"No strong match for {query!r}. Closest:", *(f"- {_entry(m)}" for m in weak[:3]), _retry(query)]
        )
    return f"No match for {query!r}. {_retry(query)}"


async def run_apropos(inp: AproposInput, ctx: ToolContext) -> CommandResult:
    commands = session_commands(ctx.session)
    # Never answer with itself: its own tags name every discovery word there is.
    searchable = [c for c in commands.values() if c.id != apropos_tool.id]
    # Plus what earlier sessions left in /shared. That directory is capability the
    # harness never declared, so nothing else can surface it, and a script a past
    # session wrote for this project is often a better answer than any command.
    searchable += shared_commands(ctx.session.project_id)
    # Plus configured MCP servers, which have no commands until activated.
    searchable += server_commands(ctx.session.project_path)
    matches = search(searchable, inp.query, limit=inp.limit)
    return CommandResult(
        stdout=_render(inp.query, matches) + "\n",
        data=AproposOutput(
            query=inp.query,
            matched=[m.command.id for m in matches],
            total=len(commands),
        ).model_dump(),
    )


apropos_tool = Tool(
    id="apropos",
    name="Apropos",
    description=(
        "Search every command by what you are trying to do — tags, guidance and "
        "examples. Run it before concluding a capability is missing."
    ),
    tags=["discover", "search", "capability", "which-command", "help", "man", "whatis",
          "shared", "scripts"],
    guidance=(
        "Query with 2-4 words of task language: `apropos 'open pull request'`. "
        "A knowledge file hit points at its best section; read that, not the file. "
        "A miss prints no list: retry with other words, then `cat /tools/index.md`. "
        "System binaries are not indexed: `compgen -c | grep -i <word>`."
    ),
    input_schema=AproposInput,
    argv=positional(joined="query", values={"limit"}),
    usage="apropos <what you are trying to do...> [--limit N]",
    output_schema=AproposOutput,
    examples=[
        CommandExample(
            command="apropos 'my sandbox will not start'",
            note="Symptoms work as well as nouns; guidance text is searched too.",
        ),
        CommandExample(
            command="apropos 'compare models on a coding task' --limit 3",
        ),
    ],
    domain=HOST,
    # Reads the session's own command registry and nothing else.
    approval=always("ALLOW"),
    run=run_apropos,
)
