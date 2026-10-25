import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.contrib.tools.history import HistoryInput, run_history
from hypergolic.harness.primitives.tool import ToolContext
from tests._factories import build_session
from tests.conftest import make_message, make_project, make_session


async def _run(query: str, as_json: bool = True):
    ctx = ToolContext(session=build_session(), broadcast=AsyncMock(), tool_id="history")
    result = await run_history(HistoryInput(query=query, as_json=as_json), ctx)
    return result, json.loads(result.stdout) if as_json and not result.is_error else None


@pytest.mark.db
async def test_select_returns_columns_rows_iso_datetimes_and_json():
    make_project()
    sid = make_session(sid="s-h")
    make_message(sid, text="findable")

    result, payload = await _run(
        "SELECT s.id, s.created_at, m.content -> 0 ->> 'text' AS t "
        "FROM sessions s JOIN messages m ON m.session_id = s.id"
    )
    assert result.exit_code == 0
    [row] = payload["rows"]
    assert payload["columns"] == ["id", "created_at", "t"]
    assert (row["id"], row["t"]) == ("s-h", "findable")
    assert datetime.fromisoformat(row["created_at"])

    _, catalog = await _run("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    assert {"sessions", "messages"} <= {r["tablename"] for r in catalog["rows"]}


@pytest.mark.db
async def test_writes_are_rejected_without_leaking_read_only_onto_the_app():
    make_project()
    for query in [
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES ('x', 's', 'user', '[]', now())",
        "UPDATE sessions SET model_tier = 'hacked'",
        "DROP TABLE sessions",
    ]:
        result, _ = await _run(query)
        assert result.is_error, query
    assert make_session(sid="s-after") == "s-after"


@pytest.mark.db
async def test_bad_sql_fails_with_the_error():
    for query in ["SELEKT * FROM nowhere", "SELECT * FROM does_not_exist"]:
        result, _ = await _run(query)
        assert result.is_error and result.stderr


@pytest.mark.parametrize("payload, stdout", [
    ({"columns": ["x", "j", "n"], "rows": [{"x": "a\tb", "j": {"k": [1]}, "n": None}]}, 'x\tj\tn\na\\tb\t{"k":[1]}\t'),
    ({"columns": ["j"], "rows": [{"j": {"t": "a\nb"}}]}, 'j\n{"t":"a\\nb"}'),
    ({"columns": ["id"], "rows": []}, "id\n(0 rows)"),
    ({"rowcount": 3}, "rowcount: 3"),
])
async def test_default_output_is_escaped_tsv(payload, stdout):
    with patch("hypergolic.contrib.tools.history._run_query_sync", return_value=payload):
        result, _ = await _run("select ...", as_json=False)
    assert result.stdout == stdout
    assert result.data == payload


def test_jsonable_values():
    from decimal import Decimal

    from hypergolic.contrib.tools.history import _jsonable

    when = datetime(2025, 1, 2, tzinfo=timezone.utc)
    assert [_jsonable(v) for v in (when, Decimal("1.5"), b"hi", b"\xff", 7)] == [
        when.isoformat(), "1.5", "hi", "ff", 7]
