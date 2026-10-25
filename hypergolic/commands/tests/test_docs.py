"""``--help`` is generated, so it can never drift from what the broker accepts."""

from typing import Any

from pydantic import Field

from hypergolic.commands.docs import approval_label, index_line, index_markdown, readme
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision, always
from hypergolic.harness.primitives.results import CommandExample, CommandResult, InputSchema
from hypergolic.harness.primitives.tool import Tool, container_domain


class QueryInput(InputSchema):
    sql: str = Field(description="The statement to run.")
    limit: int = 10


class QueryOutput(InputSchema):
    rows: list[dict] = []


async def _run(_inp, _ctx):
    return CommandResult(stdout="")


def query_command(**overrides) -> Tool:
    fields: dict[str, Any] = dict(
        id="query",
        name="Query",
        description="Ask the database something.",
        usage="query <sql> [--limit N]",
        guidance="Prefer narrow columns.",
        input_schema=QueryInput,
        output_schema=QueryOutput,
        examples=[CommandExample(command="query 'select 1' | jq .rows", note="Pipe it.")],
        approval=always("ALLOW"),
        run=_run,
    )
    fields.update(overrides)
    return Tool(**fields)


def test_readme_carries_usage_arguments_output_and_examples():
    text = readme(query_command())
    assert "query <sql> [--limit N]" in text
    assert "The statement to run." in text
    assert "`limit`" in text and "default `10`" in text
    assert "`rows`" in text
    assert "query 'select 1' | jq .rows" in text
    assert "Prefer narrow columns." in text


def test_readme_states_provenance_and_approval_posture():
    text = readme(query_command(origin="skill:database", domain=container_domain("db")))
    assert "skill:database" in text
    assert "container `db`" in text
    assert "auto-approved" in text


def test_advisory_readme_says_there_is_nothing_to_run():
    text = readme(Tool(id="acme-database", name="Acme DB", description="How to"))
    assert "/tools/bin/acme-database" in text
    assert "Usage" not in text


def test_approval_label_reports_a_policy_it_cannot_summarize():
    def per_argument(ctx: ApprovalContext) -> ToolApprovalDecision:
        assert ctx.input is not None  # a policy that needs its arguments
        return ToolApprovalDecision(decision="ALLOW")

    assert "read `source`" in approval_label(query_command(approval=per_argument))


def test_approval_label_spells_out_a_total_policy():
    label = approval_label(query_command(approval=always("REQUIRE_APPROVAL", "it merges")))
    assert label == "requires human approval \u2014 it merges"
    assert approval_label(query_command(approval=always("DENY"))) == "always denied"


def test_index_line_answers_when_not_how():
    assert index_line(query_command()) == "query \u2014 Ask the database something."
    advisory = Tool(id="guide", name="Guide", description="Read first.")
    assert index_line(advisory) == "guide (docs only) \u2014 Read first."


def test_index_is_sorted_so_the_prompt_prefix_stays_stable():
    commands = {"b": query_command(id="b"), "a": query_command(id="a")}
    body = index_markdown(commands)
    assert body.index("- a ") < body.index("- b ")
