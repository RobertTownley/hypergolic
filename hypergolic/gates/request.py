from __future__ import annotations

import time
from dataclasses import dataclass, field

from hypergolic.git.sandbox_integrate import RepoSlot
from hypergolic.harness.project import Project
from hypergolic.messages.types import BroadcastFn
from hypergolic.schemas import Session


@dataclass
class LandRequest:
    """Everything a gate needs to evaluate one candidate."""

    session: Session
    project: Project
    slot: RepoSlot
    base_sha: str
    candidate: str
    candidate_ref: str
    message: str
    broadcast: BroadcastFn
    description: str = ""


@dataclass
class GateVerdict:
    ok: bool
    lines: list[str] = field(default_factory=list)


def passed(label: str, started: float) -> str:
    return f"✓ {label} ({time.monotonic() - started:.0f}s)"
