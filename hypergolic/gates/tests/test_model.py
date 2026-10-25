import pytest

from hypergolic.gates.model import (
    AgenticReview,
    Check,
    Parallel,
    SandboxRepo,
    UserApproval,
    default_gates,
    default_harness_gates,
    pipeline_for,
)


def test_bare_gate_defaults_to_app():
    gate = UserApproval()
    assert gate.applies_to(SandboxRepo.APP)
    assert not gate.applies_to(SandboxRepo.SHARED)


def test_repo_accepts_single_value_and_sets():
    assert UserApproval(repo=SandboxRepo.HARNESS).repos == {SandboxRepo.HARNESS}
    both = UserApproval(repo={SandboxRepo.APP, SandboxRepo.SHARED})
    assert both.applies_to(SandboxRepo.SHARED)


def test_parallel_children_inherit_group_repo():
    group = Parallel(
        Check(name="t", cmd="true"), repo=SandboxRepo.SHARED,
    )
    assert group.applies_to(SandboxRepo.SHARED)
    assert not group.applies_to(SandboxRepo.APP)


def test_parallel_child_contradiction_is_an_error():
    with pytest.raises(ValueError, match="Parallel group"):
        Parallel(
            Check(name="t", cmd="true", repo=SandboxRepo.HARNESS),
            repo=SandboxRepo.APP,
        )


def test_parallel_requires_children():
    with pytest.raises(ValueError):
        Parallel()


def test_pipeline_filters_and_orders():
    gates = [
        Parallel(
            Check(name="tests", cmd="pytest"),
            Check(name="lint", cmd="ruff", repo={SandboxRepo.APP}),
        ),
        AgenticReview(repo={SandboxRepo.APP, SandboxRepo.SHARED}),
        UserApproval(),
    ]
    app = pipeline_for(gates, SandboxRepo.APP)
    assert [g.label for g in app] == ["parallel", "agentic review", "user approval"]
    shared = pipeline_for(gates, SandboxRepo.SHARED)
    assert [g.label for g in shared] == ["agentic review"]
    assert pipeline_for(gates, SandboxRepo.HARNESS) == []


def test_pipeline_collapses_single_child_parallel():
    gates = [
        Parallel(
            Check(name="tests", cmd="pytest", repo=SandboxRepo.APP),
            Check(name="shared-only", cmd="x", repo=SandboxRepo.SHARED),
            repo={SandboxRepo.APP, SandboxRepo.SHARED},
        ),
    ]
    shared = pipeline_for(gates, SandboxRepo.SHARED)
    assert len(shared) == 1 and shared[0].label == "shared-only"


def test_pipeline_narrows_children_with_superset_repo_sets():
    both = {SandboxRepo.APP, SandboxRepo.SHARED}
    gates = [
        Parallel(
            Check(name="tests", cmd="pytest", repo=both),
            Check(name="lint", cmd="ruff", repo=both),
            repo=both,
        ),
    ]
    app = pipeline_for(gates, SandboxRepo.APP)
    assert len(app) == 1 and isinstance(app[0], Parallel)
    assert all(c.repos == {SandboxRepo.APP} for c in app[0].gates)
    collapsed = pipeline_for(
        [Parallel(Check(name="tests", cmd="pytest", repo=both), repo=both)],
        SandboxRepo.SHARED,
    )
    assert collapsed[0].repos == {SandboxRepo.SHARED}


def test_defaults():
    assert [g.label for g in default_gates()] == ["user approval"]
    assert default_harness_gates()[0].applies_to(SandboxRepo.HARNESS)
