"""Tests for the /api/system router."""

from unittest.mock import patch
from hypergolic.enums import ModelTier
from hypergolic.harness.app import state as app_state


def test_open_url_http_invokes_webbrowser(api_client):
    with patch("hypergolic.system.router.webbrowser.open", return_value=True) as mock_open:
        resp = api_client.post("/api/system/open-url", json={"url": "http://example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"opened": True}
    mock_open.assert_called_once_with("http://example.com")


def test_open_url_https_invokes_webbrowser(api_client):
    with patch("hypergolic.system.router.webbrowser.open", return_value=True) as mock_open:
        resp = api_client.post("/api/system/open-url", json={"url": "https://example.com/path?q=1"})
    assert resp.status_code == 200
    assert resp.json() == {"opened": True}
    mock_open.assert_called_once_with("https://example.com/path?q=1")


def test_open_url_strips_whitespace(api_client):
    with patch("hypergolic.system.router.webbrowser.open", return_value=True) as mock_open:
        resp = api_client.post("/api/system/open-url", json={"url": "  https://example.com  "})
    assert resp.status_code == 200
    mock_open.assert_called_once_with("https://example.com")


def test_open_url_rejects_non_http_scheme(api_client):
    with patch("hypergolic.system.router.webbrowser.open") as mock_open:
        resp = api_client.post("/api/system/open-url", json={"url": "file:///etc/passwd"})
    assert resp.status_code == 400
    mock_open.assert_not_called()


def test_open_url_rejects_javascript_scheme(api_client):
    with patch("hypergolic.system.router.webbrowser.open") as mock_open:
        resp = api_client.post("/api/system/open-url", json={"url": "javascript:alert(1)"})
    assert resp.status_code == 400
    mock_open.assert_not_called()


def test_open_url_returns_opened_false_when_webbrowser_fails(api_client):
    with patch("hypergolic.system.router.webbrowser.open", return_value=False):
        resp = api_client.post("/api/system/open-url", json={"url": "https://example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"opened": False}


def test_get_system_config_returns_default_model_tier(api_client):
    resp = api_client.get("/api/system/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "default_model_tier" in data
    assert data["default_model_tier"] in ("Low", "Medium", "High")
    assert isinstance(data["truncate_token_threshold"], int)


def test_get_system_config_reflects_app_setting(api_client, monkeypatch):
    class _FakeApp:
        default_model_tier = ModelTier.MEDIUM
        truncate_token_threshold = 42_000

    monkeypatch.setattr(app_state, "_current_app", _FakeApp())
    resp = api_client.get("/api/system/config")
    assert resp.status_code == 200
    assert resp.json()["default_model_tier"] == "Medium"
    assert resp.json()["truncate_token_threshold"] == 42_000
