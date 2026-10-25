"""System-level endpoints (e.g. opening URLs in the host OS browser)."""

from __future__ import annotations

import webbrowser

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hypergolic.enums import ModelTier
from hypergolic.harness.app.state import get_app

router = APIRouter(prefix="/api/system", tags=["system"])


class OpenUrlRequest(BaseModel):
    url: str


class OpenUrlResponse(BaseModel):
    opened: bool


class SystemConfig(BaseModel):
    default_model_tier: ModelTier
    truncate_token_threshold: int


@router.get("/config", response_model=SystemConfig)
def get_system_config() -> SystemConfig:
    """Return app-level configuration the UI needs at startup."""
    app = get_app()
    return SystemConfig(
        default_model_tier=app.default_model_tier,
        truncate_token_threshold=app.truncate_token_threshold,
    )


@router.post("/open-url", response_model=OpenUrlResponse)
def open_url(payload: OpenUrlRequest) -> OpenUrlResponse:
    """Open a URL in the host system's default browser.

    Only http(s) URLs are permitted to prevent the webview from being used
    as a vector for invoking other URL-handler schemes.
    """
    url = payload.url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="Only http(s) URLs are allowed")
    opened = webbrowser.open(url)
    return OpenUrlResponse(opened=opened)
