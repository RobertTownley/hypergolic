"""Tests for hypergolic.dispatch.state."""
import asyncio
from unittest.mock import MagicMock

from hypergolic.dispatch.state import (
    DispatchResult,
    _child_to_parent,
    _pending_dispatches,
    register_turn_runner,
    resolve_dispatch,
)
import hypergolic.dispatch.state as _state


def _clear():
    _pending_dispatches.clear()
    _child_to_parent.clear()


def test_resolve_dispatch_resolves_future():
    _clear()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        _pending_dispatches["child-1"] = future
        _child_to_parent["child-1"] = "parent-1"

        result = resolve_dispatch("child-1", DispatchResult(outcome="success", conclusion="done"))
        assert result is True
        assert future.result().outcome == "success"
        assert "child-1" not in _pending_dispatches
        assert "child-1" not in _child_to_parent
    finally:
        loop.close()


def test_resolve_dispatch_returns_false_when_no_future():
    _clear()
    result = resolve_dispatch("nonexistent", DispatchResult(outcome="success", conclusion="done"))
    assert result is False


def test_resolve_dispatch_returns_false_when_future_done():
    _clear()
    loop = asyncio.new_event_loop()
    try:
        future = loop.create_future()
        future.set_result(DispatchResult(outcome="success", conclusion="already done"))
        _pending_dispatches["child-2"] = future

        result = resolve_dispatch("child-2", DispatchResult(outcome="failure", conclusion="late"))
        assert result is False
    finally:
        loop.close()


def test_register_turn_runner():
    original = _state._turn_runner
    try:
        runner = MagicMock()
        register_turn_runner(runner)
        assert _state._turn_runner is runner
    finally:
        _state._turn_runner = original
