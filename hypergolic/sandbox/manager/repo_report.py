"""Per-session repo-convergence reports, for readiness probes and the `cmd`
tool's post-start warning. In-memory on purpose: a report is only meaningful
for containers this process brought up."""

from dataclasses import dataclass


class RepoProvisionError(Exception):
    """A sandbox-owned repo could not be provisioned."""


@dataclass
class RepoStep:
    """One converge step's outcome; ``ok=None`` means skipped."""

    repo: str
    action: str  # "clone" | "heal" | "ensure" | "skip"
    ok: bool | None
    detail: str = ""
    fix: str = ""


_reports: dict[str, list[RepoStep]] = {}


def record_report(session_id: str, steps: list[RepoStep]) -> None:
    _reports[session_id] = steps


def pop_report_warnings(session_id: str) -> list[str]:
    """Failure lines from the last convergence, cleared on read so the agent
    is warned once per (re)start rather than once per command."""
    steps = _reports.pop(session_id, [])
    return [f"/{s.repo}: {s.action} failed: {s.detail}" for s in steps if s.ok is False]
