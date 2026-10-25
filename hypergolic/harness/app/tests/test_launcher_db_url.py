"""The launcher must not clobber an explicitly configured database URL."""

from unittest.mock import patch

import pytest

from hypergolic.config.settings import Settings, settings
from hypergolic.harness.app.core import App
from hypergolic.harness.app.launcher import _redact_url, launch


def _launch_and_capture(app: App) -> str:
    """Run launch() far enough to settle the DB URL, then stop."""
    seen: list[str] = []

    def fake_migrations() -> None:
        seen.append(settings.HYPERGOLIC_DATABASE_URL)
        raise _Stop

    with patch("hypergolic.harness.app.launcher.run_migrations", fake_migrations):
        try:
            launch(app)
        except _Stop:
            pass
    return seen[0]


class _Stop(Exception):
    pass


@pytest.fixture(autouse=True)
def _no_telemetry():
    """launch() installs process-global OTel providers; keep them out of tests."""
    with (
        patch("hypergolic.harness.app.launcher.start_telemetry"),
        patch("hypergolic.harness.app.launcher.start_telemetry_backend"),
    ):
        yield


def test_configured_url_skips_container_management(monkeypatch):
    url = "postgresql://u:pw@localhost:5432/hypergolic"
    monkeypatch.setattr(settings, "HYPERGOLIC_DATABASE_URL", url)
    monkeypatch.setattr(
        type(settings), "model_fields_set", {"HYPERGOLIC_DATABASE_URL"}, raising=False
    )
    with patch("hypergolic.db.container.ensure_postgres") as ensure:
        assert _launch_and_capture(App()) == url
    ensure.assert_not_called()


def test_default_url_brings_up_managed_container(monkeypatch):
    monkeypatch.setattr(type(settings), "model_fields_set", set(), raising=False)
    with (
        patch("hypergolic.db.container.docker_running", return_value=True),
        patch("hypergolic.db.container.ensure_postgres") as ensure,
    ):
        _launch_and_capture(App())
    ensure.assert_called_once()


def test_env_var_marks_field_as_explicitly_set(monkeypatch):
    """The launcher's managed-vs-configured check relies on this pydantic behavior."""
    monkeypatch.setenv("HYPERGOLIC_DATABASE_URL", "postgresql://u:p@h/db")
    assert "HYPERGOLIC_DATABASE_URL" in Settings().model_fields_set

    monkeypatch.delenv("HYPERGOLIC_DATABASE_URL")
    assert "HYPERGOLIC_DATABASE_URL" not in Settings().model_fields_set


def test_redact_url_hides_password():
    assert (
        _redact_url("postgresql://user:secret@host:5432/db")
        == "postgresql://user:***@host:5432/db"
    )
    assert _redact_url("postgresql://host/db") == "postgresql://host/db"
