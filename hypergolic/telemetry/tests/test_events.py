import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hypergolic.telemetry.events import emit
from hypergolic.telemetry.router import router


def test_emit_logs_name_and_attributes(caplog):
    with caplog.at_level(logging.INFO, logger="hypergolic.events"):
        emit("approval.replied", session_id="S1", approved=False, reason=None)
    record = caplog.records[-1]
    assert record.getMessage() == "event approval.replied session=S1 approved=False"
    assert getattr(record, "event.name") == "approval.replied"
    assert getattr(record, "event.approved") is False
    assert getattr(record, "session.id") == "S1"
    assert not hasattr(record, "event.reason")


def test_ui_event_is_prefixed_and_validated(caplog):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    with caplog.at_level(logging.INFO, logger="hypergolic.events"):
        ok = client.post("/api/telemetry/events", json={
            "name": "hotkey.used", "attrs": {"hotkey": "Mod+J"},
        })
    assert ok.status_code == 204
    assert getattr(caplog.records[-1], "event.name") == "ui.hotkey.used"
    bad = client.post("/api/telemetry/events", json={"name": "Bad Name!"})
    assert bad.status_code == 422
