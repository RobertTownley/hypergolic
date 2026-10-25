"""`apropos` is the way down from a one-line index; a miss must not dead-end."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pathlib import Path

from hypergolic.commands.registry import advisory_command
from hypergolic.commands.shared_index import SharedScript, as_command
from hypergolic.config.schemas import MCPServerConfig
from hypergolic.mcptools.discovery import server_commands
from hypergolic.contrib.tools.apropos import AproposInput, apropos_tool
from hypergolic.harness.primitives.bundles import Skill
from hypergolic.harness.primitives.tool import Tool, ToolContext
from tests._factories import build_session, invoke

pytestmark = pytest.mark.timeout(10)


def _commands() -> dict[str, Tool]:
    doctor = advisory_command(
        Skill(
            id="sandbox-doctor",
            name="Sandbox Doctor",
            description="Diagnose a sandbox that will not start.",
            tags=["sandbox", "docker"],
        ),
        origin="skill:sandbox-doctor",
        guidance="",
    )
    return {c.id: c for c in (doctor, apropos_tool)}


async def _run(
    query: str,
    monkeypatch,
    shared: list[Tool] | None = None,
    servers: list[Tool] | None = None,
) -> str:
    monkeypatch.setattr(
        "hypergolic.contrib.tools.apropos.session_commands", lambda _session: _commands()
    )
    monkeypatch.setattr(
        "hypergolic.contrib.tools.apropos.shared_commands", lambda _project: shared or []
    )
    monkeypatch.setattr(
        "hypergolic.contrib.tools.apropos.server_commands", lambda _path: servers or []
    )
    ctx = ToolContext(session=build_session(), broadcast=AsyncMock(), tool_id="apropos")
    result = await invoke(apropos_tool, AproposInput(query=query), ctx)
    return result.stdout


async def test_a_hit_names_the_command_without_its_tags(monkeypatch):
    out = await _run("my sandbox will not start", monkeypatch)
    assert "sandbox-doctor (docs only)" in out
    assert "docker" not in out
    assert "--help" in out


async def test_a_near_miss_is_reported_as_a_guess_rather_than_an_answer(monkeypatch):
    """One incidental word is not an answer: `sandbox-doctor` matches "diagnose a
    design" too, and a confident list of near-misses stops the agent looking."""
    out = await _run("diagnose a design mock", monkeypatch)
    assert "No strong match" in out
    assert "sandbox-doctor" in out
    assert "compgen -c | grep -i diagnose" in out


async def test_a_miss_is_one_line_that_points_at_the_index(monkeypatch):
    out = await _run("resize a png", monkeypatch)
    assert "No match" in out
    assert "sandbox-doctor" not in out
    assert "cat /tools/index.md" in out
    assert "compgen -c | grep -i resize" in out


async def test_it_never_answers_with_itself(monkeypatch):
    """Its own tags name every discovery word there is, so it would win always."""
    out = await _run("search for a command", monkeypatch)
    assert "- apropos" not in out


async def test_a_shared_script_is_offered_with_the_line_that_runs_it(monkeypatch):
    """`/shared` is capability the harness never declared, so nothing else surfaces
    it, and `--help` would be a lie: the next step is the command line itself."""
    shared = [
        as_command(
            SharedScript(
                path=Path("seed.py"),
                summary="Seed the staging database.",
                body="",
                tags=["seed", "staging"],
            )
        )
    ]
    out = await _run("seed staging", monkeypatch, shared=shared)
    assert "seed.py \u2014 Seed the staging database." in out
    assert "\u2192  uv run /shared/seed.py" in out
    assert "read before running" in out


async def test_a_knowledge_hit_points_at_its_best_section(monkeypatch):
    body = "# Tracker\nintro\n## Creating a ticket\ncreate\n## Updating a ticket\nupdate status\n"
    shared = [
        as_command(
            SharedScript(path=Path("knowledge/tracker.md"), summary="Tracker", body=body, tags=[])
        )
    ]
    out = await _run("update tracker", monkeypatch, shared=shared)
    assert "sed -n 5,6p /shared/knowledge/tracker.md" in out
    assert "Updating a ticket" in out


async def test_an_unconnected_mcp_server_is_found_by_what_it_reaches(monkeypatch):
    """Before activation a server lists no tools, so its declared description and
    tags are the only way an agent learns it reads chat."""
    manager = MagicMock()
    manager.get_available_servers.return_value = {
        "acme-mcp-gateway": (
            MCPServerConfig(description="Internal services: chat, log search", tags=["chat"]),
            "user",
        )
    }
    monkeypatch.setattr("hypergolic.mcptools.client.manager.get_mcp_manager", lambda: manager)
    out = await _run("read a chat channel", monkeypatch, servers=server_commands(None))
    assert "acme-mcp-gateway (MCP server) \u2014 Internal services: chat, log search" in out
    assert "\u2192  mcp activate acme-mcp-gateway" in out
    assert "--help" not in out
