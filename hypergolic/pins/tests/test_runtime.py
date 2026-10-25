from hypergolic.harness.app.core import App
from hypergolic.pins import runtime as rt
from hypergolic.pins.runtime import pin_app, pinned_app


def test_pin_app_routes_the_session_through_its_app():
    app = App()
    pin_app("S1", app)
    assert pinned_app("S1") is app
    assert pinned_app("S2") is None


def test_drop_live_derived_pins_keeps_snapshot_sessions(monkeypatch):
    monkeypatch.setattr(rt, "_pinned_apps", {})
    monkeypatch.setattr(rt, "_snapshot_users", {})
    override_app, snapshot_app = App(), App()
    pin_app("OVR", override_app)
    pin_app("SNAP", snapshot_app)
    rt.register_snapshot_use("SNAP", "abc123")

    assert rt.drop_live_derived_pins() == ["OVR"]
    assert pinned_app("OVR") is None
    assert pinned_app("SNAP") is snapshot_app
