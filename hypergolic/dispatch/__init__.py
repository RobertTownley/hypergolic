"""Public dispatch API for harness tool and skill authors.

These are the stable entry points for building custom multi-agent tools.
"""
from hypergolic.dispatch.runner import CONCLUDE_INSTRUCTION, dispatch, send_turn
from hypergolic.dispatch.state import DispatchResult, register_turn_runner, resolve_dispatch
from hypergolic.sessions.operations import create_session

__all__ = [
    "CONCLUDE_INSTRUCTION",
    "DispatchResult",
    "create_session",
    "dispatch",
    "register_turn_runner",
    "resolve_dispatch",
    "send_turn",
]
