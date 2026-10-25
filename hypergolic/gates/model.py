"""Declarative landing-gate pipelines.

A ``git push origin HEAD:<branch>`` from a session sandbox becomes a land request;
the ordered subset of the project's ``merge_gates`` matching the pushed repo
runs, and the push succeeds only if every gate passes. List position is
execution order; :class:`Parallel` is the only concurrency primitive.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from collections.abc import Sequence

from pydantic import BaseModel, Field, field_validator, model_validator

from hypergolic.enums import ModelTier

#: What to do when the base branch moved while gates ran (GitHub's
#: "require branches to be up to date", inverted; see the PRD).
OnStaleBase = Literal["land", "regate", "reject"]

#: How `land` puts pushed commits on the host branch: squash them into one
#: commit, or fast-forward the branch to the pushed sha as-is (history and
#: merge commits preserved; a moved base is rejected rather than rebased).
LandMode = Literal["squash", "fast-forward"]


class SandboxRepo(StrEnum):
    APP = "app"
    HARNESS = "harness"
    SHARED = "shared"


class _Gate(BaseModel):
    """Base gate: carries only the repo filter.

    ``repo=None`` means "unspecified": a bare gate defaults to APP, a child
    of a :class:`Parallel` inherits its group's repos.
    """

    repo: SandboxRepo | set[SandboxRepo] | frozenset[SandboxRepo] | None = None

    model_config = {"frozen": True}

    @field_validator("repo", mode="before")
    @classmethod
    def _coerce_repo(cls, v: object) -> object:
        if v is None or isinstance(v, frozenset):
            return v
        if isinstance(v, (set, list, tuple)):
            return frozenset(v)
        return frozenset({v})

    @property
    def repos(self) -> frozenset[SandboxRepo]:
        if isinstance(self.repo, frozenset):
            return self.repo
        return frozenset({SandboxRepo.APP})

    def applies_to(self, repo: SandboxRepo) -> bool:
        return repo in self.repos


class Check(_Gate):
    """A shell command run in a fresh sandboxed checkout of the merge candidate."""

    name: str
    cmd: str
    timeout: int = 600
    env: dict[str, str] = Field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.name


class AgenticReview(_Gate):
    """A reviewer-role subagent pointed at the candidate diff."""

    focus: str = ""
    model_tier: ModelTier | None = None

    @property
    def label(self) -> str:
        return "agentic review"


class UserApproval(_Gate):
    """The human reviews the candidate diff in the merge-review takeover."""

    @property
    def label(self) -> str:
        return "user approval"


class Parallel(_Gate):
    """Run child gates concurrently. Only non-interactive gates may nest."""

    gates: tuple[Check | AgenticReview, ...] = ()

    def __init__(self, *gates: Check | AgenticReview, **kwargs: Any) -> None:
        if gates:
            kwargs["gates"] = gates
        super().__init__(**kwargs)

    @model_validator(mode="after")
    def _validate_children(self) -> "Parallel":
        if not self.gates:
            raise ValueError("Parallel() needs at least one child gate")
        for child in self.gates:
            if child.repo is not None and not child.repos <= self.repos:
                raise ValueError(
                    f"gate {child.label!r} targets {set(child.repo)} but its "
                    f"Parallel group only covers {set(self.repos)}"
                )
        return self

    @property
    def label(self) -> str:
        return "parallel"

    def applies_to(self, repo: SandboxRepo) -> bool:
        return any(_child_applies(c, self, repo) for c in self.gates)


Gate = Check | AgenticReview | UserApproval | Parallel


def _child_applies(child: Check | AgenticReview, group: Parallel, repo: SandboxRepo) -> bool:
    return repo in (child.repos if child.repo is not None else group.repos)


def default_gates() -> list[Gate]:
    """Today's behavior: every /app land needs the human's approval."""
    return [UserApproval()]


def default_harness_gates() -> list[Gate]:
    return [UserApproval(repo=SandboxRepo.HARNESS)]


def pipeline_for(gates: Sequence[Gate], repo: SandboxRepo) -> list[Gate]:
    """The ordered filter of *gates* that applies to a push to *repo*.

    A ``Parallel`` narrows to its applicable children; a group left with one
    child collapses to that child.
    """
    out: list[Gate] = []
    for gate in gates:
        if isinstance(gate, Parallel):
            kids = [
                c.model_copy(update={"repo": frozenset({repo})})
                for c in gate.gates
                if _child_applies(c, gate, repo)
            ]
            if len(kids) == 1:
                out.append(kids[0])
            elif kids:
                out.append(Parallel(*kids, repo=frozenset({repo})))
        elif gate.applies_to(repo):
            out.append(gate)
    return out
