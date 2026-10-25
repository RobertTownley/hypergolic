"""Resolving which gates a land request must pass."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hypergolic.gates.model import (
    Gate,
    SandboxRepo,
    default_gates,
    default_harness_gates,
    pipeline_for,
)

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App
    from hypergolic.harness.project import Project


def gates_for(app: "App", project: "Project", repo: SandboxRepo) -> list[Gate]:
    """The ordered pipeline for a push to *repo*.

    /app and /shared read the project's ``merge_gates``; /harness reads the
    app-level pipeline only, so no project's laxity ungates config edits.
    """
    if repo is SandboxRepo.HARNESS:
        declared: list[Gate] | None = app.harness_merge_gates
        if declared is None:
            return pipeline_for(default_harness_gates(), repo)
        scoped = [
            g.model_copy(update={"repo": frozenset({repo})}) if g.repo is None else g
            for g in declared
        ]
        return pipeline_for(scoped, repo)
    declared = project.merge_gates
    return pipeline_for(declared if declared is not None else default_gates(), repo)
