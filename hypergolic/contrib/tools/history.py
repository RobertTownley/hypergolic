import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from hypergolic.config.settings import settings
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.eval_behavior import always_conduct
from hypergolic.harness.primitives.results import CommandExample, CommandResult, InputSchema
from hypergolic.harness.primitives.tool import HOST, Tool, ToolContext
from hypergolic.commands.argv import positional

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine


class HistoryInput(InputSchema):
    query: str
    as_json: bool = False


class HistoryOutput(InputSchema):
    columns: list[str] = []
    rows: list[dict] = []
    rowcount: int | None = None


def _get_engine_for_query() -> "Engine":
    """A fresh read-only engine per call, so the read-only setting never
    leaks into the app's main engine. Read-only rides the server connection
    options: a SET on a cursor would open an implicit transaction that the
    pool's reset rolls back, silently undoing it."""
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    from hypergolic.db.engine import sync_url

    return create_engine(
        sync_url(settings.HYPERGOLIC_DATABASE_URL),
        poolclass=NullPool,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value.hex()
    return value


def _run_query_sync(query: str) -> dict[str, Any]:
    from sqlalchemy import text

    engine = _get_engine_for_query()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(query))
            if result.returns_rows:
                columns = list(result.keys())
                rows = [
                    {col: _jsonable(val) for col, val in zip(columns, row)}
                    for row in result.fetchall()
                ]
                return {"columns": columns, "rows": rows}
            return {"rowcount": result.rowcount}
    finally:
        engine.dispose()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return json.dumps(value, separators=(",", ":"), default=str)
    return value.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n")


def _tsv(payload: dict[str, Any]) -> str:
    if "rowcount" in payload:
        return f"rowcount: {payload['rowcount']}"
    cols = payload["columns"]
    lines = ["\t".join(cols)]
    lines += ["\t".join(_cell(row[c]) for c in cols) for row in payload["rows"]]
    return "\n".join(lines) if payload["rows"] else lines[0] + "\n(0 rows)"


async def run_history(inp: HistoryInput, _ctx: ToolContext) -> CommandResult:
    try:
        payload = await asyncio.to_thread(_run_query_sync, inp.query)
    except Exception as e:
        return CommandResult.fail(f"{type(e).__name__}: {e}")
    stdout = json.dumps(payload, default=str) if inp.as_json else _tsv(payload)
    return CommandResult(stdout=stdout, data=payload)


history_command = Tool(
    id="history",
    tags=["sql", "database", "analytics", "telemetry", "sessions", "transcripts",
        "approvals", "usage", "evidence"],
    name="History",
    description=(
        "Query Hypergolic's own database with SQL — sessions, messages, tool "
        "calls, approvals — to ground a claim about how the harness is actually used."
    ),
    usage="history <sql...> [--json]",
    guidance=(
        "Read-only: the connection opens with default_transaction_read_only "
        "on (Postgres), so a write fails rather than being silently accepted. "
        "Output is TSV: a header row, then one row per line; tabs, newlines "
        "and backslashes in a value are escaped, and JSON values are compact "
        "JSON. `--json` prints {columns, rows} for `jq` or scripts. Select "
        "narrow columns rather than paging a wide result."
    ),
    input_schema=HistoryInput,
    output_schema=HistoryOutput,
    examples=[
        CommandExample(
            command=(
                "history 'select tool_name, count(*) c from tool_approvals "
                "group by 1 order by c desc'"
            ),
            note="Which capability actually gets used, ranked.",
        ),
        CommandExample(
            command=(
                "history 'select id, role from sessions order by created_at "
                "desc limit 5' --json | jq .rows"
            ),
        ),
    ],
    domain=HOST,
    # Read-only and therefore safe to leave ungated, which is the whole point:
    # anything auto-approved is reachable by any code running in the sandbox, so
    # the decision has to be deliberate rather than a default.
    approval=always("ALLOW"),
    eval_behavior=always_conduct,
    argv=positional(joined="query", bools={"json"}, remap={"json": "as_json"}),
    run=run_history,
)

history_tool = history_command
