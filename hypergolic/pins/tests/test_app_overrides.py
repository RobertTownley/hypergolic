from hypergolic.harness.app.core import App
from hypergolic.harness.primitives.bundles import Role
from hypergolic.pins.app_overrides import overridden_app


def _app() -> App:
    app = App(truncate_token_threshold=100, strip_history_thinking=True)
    app.register_roles([Role(id="reviewer", name="Reviewer", prompt="r", strip_history_thinking=True)])
    return app


def test_override_sets_values_on_a_copy():
    base = _app()
    app = overridden_app(base, {"truncate_token_threshold": 7})
    assert app.truncate_token_threshold == 7
    assert base.truncate_token_threshold == 100
    assert app.roles is base.roles


def test_strip_history_thinking_override_reaches_every_role():
    base = _app()
    app = overridden_app(base, {"strip_history_thinking": False})
    assert app.strip_history_thinking is False
    assert [r.strip_history_thinking for r in app.roles] == [False]
    assert [r.strip_history_thinking for r in base.roles] == [True]
