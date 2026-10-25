from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from hypergolic.telemetry.events import emit
from hypergolic.telemetry.status import telemetry_status

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


class UiEvent(BaseModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.]{0,63}$")
    session_id: str | None = None
    attrs: dict[str, str | int | float | bool | None] = Field(default_factory=dict, max_length=16)


@router.get("/status")
def get_telemetry_status() -> dict[str, Any]:
    """Whether each OTLP signal leaves the process, and where it stops if not."""
    return telemetry_status()


@router.post("/events", status_code=204)
def post_ui_event(event: UiEvent) -> None:
    emit(f"ui.{event.name}", session_id=event.session_id, **event.attrs)
