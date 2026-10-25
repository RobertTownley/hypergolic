"""Materialization fails loudly at import rather than degrading a live session."""

from typing import Any

import pytest

from hypergolic.commands.validate import (
    CommandValidationError,
    assert_valid,
    validate_commands,
)
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import CommandResult, InputSchema
from hypergolic.harness.primitives.tool import Tool, container_domain


async def _run(_inp, _ctx):
    return CommandResult()


def command(cid: str, **overrides) -> Tool:
    fields: dict[str, Any] = dict(
        id=cid,
        name=cid,
        description=f"The {cid} command.",
        approval=always("ALLOW"),
        run=_run,
    )
    fields.update(overrides)
    return Tool(**fields)


def test_a_valid_set_has_no_problems():
    assert validate_commands([command("gh"), command("history")]) == []


def test_two_origins_cannot_ship_the_same_name():
    problems = validate_commands(
        [command("gh", origin="skill:a"), command("gh", origin="skill:b")]
    )
    assert len(problems) == 1
    assert "skill:a" in problems[0] and "skill:b" in problems[0]


def test_a_command_named_test_would_shadow_a_binary_the_shell_needs():
    problems = validate_commands([command("test")])
    assert "shadow" in problems[0]


def test_an_advisory_command_may_take_a_reserved_name():
    assert validate_commands([Tool(id="test", name="test", description="docs")]) == []


def test_an_id_that_is_not_a_filename_is_rejected():
    assert validate_commands([command("skills/db")])
    assert validate_commands([command(".hidden")])


def test_an_invocable_command_without_a_description_cannot_be_found():
    problems = validate_commands([command("gh", description=" ")])
    assert "relevance index" in problems[0]


def test_a_container_domain_must_name_a_container_the_session_declares():
    target = command("psql", domain=container_domain("db"))
    assert validate_commands([target], known_containers={"db"}) == []
    problems = validate_commands([target], known_containers={"dev"})
    assert "does not declare" in problems[0]


def test_a_broken_schema_is_caught_before_it_reaches_the_agent():
    class Broken(InputSchema):
        value: "Unresolvable"  # ty: ignore[unresolved-reference]  # noqa: F821

    problems = validate_commands([command("probe", input_schema=Broken)])
    assert "input_schema is invalid" in problems[0]


def test_assert_valid_lists_every_problem_at_once():
    with pytest.raises(CommandValidationError) as excinfo:
        assert_valid([command("test"), command("cat")])
    message = str(excinfo.value)
    assert "test" in message and "cat" in message
