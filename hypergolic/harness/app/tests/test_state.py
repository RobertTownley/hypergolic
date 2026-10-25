import pytest

from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import app_context, get_app, set_app


def test_app_context_overrides_and_restores():
    base, pinned = App(), App()
    set_app(base)
    assert get_app() is base
    with app_context(pinned):
        assert get_app() is pinned
        with app_context(base):
            assert get_app() is base
        assert get_app() is pinned
    assert get_app() is base


def test_app_context_restores_on_error():
    base, pinned = App(), App()
    set_app(base)
    with pytest.raises(RuntimeError):
        with app_context(pinned):
            raise RuntimeError("boom")
    assert get_app() is base
