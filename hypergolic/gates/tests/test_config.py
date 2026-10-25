from types import SimpleNamespace

from hypergolic.gates.config import gates_for
from hypergolic.gates.model import Check, SandboxRepo, UserApproval


def _app(harness_gates=None):
    return SimpleNamespace(harness_merge_gates=harness_gates)


def _project(gates=None):
    return SimpleNamespace(merge_gates=gates)


def test_default_project_pipeline_gates_app_only():
    app, project = _app(), _project()
    assert gates_for(app, project, SandboxRepo.APP) == [UserApproval()]
    assert gates_for(app, project, SandboxRepo.SHARED) == []


def test_empty_pipeline_means_ungated():
    assert gates_for(_app(), _project([]), SandboxRepo.APP) == []


def test_harness_reads_app_level_config_never_project():
    lax_project = _project([])
    assert gates_for(_app(), lax_project, SandboxRepo.HARNESS) == [
        UserApproval(repo=SandboxRepo.HARNESS),
    ]
    custom = [Check(name="validate", cmd="hg validate", repo=SandboxRepo.HARNESS)]
    assert gates_for(_app(custom), lax_project, SandboxRepo.HARNESS) == custom


def test_shared_gated_only_when_named():
    project = _project([UserApproval(repo={SandboxRepo.APP, SandboxRepo.SHARED})])
    assert gates_for(_app(), project, SandboxRepo.SHARED) == [
        UserApproval(repo={SandboxRepo.APP, SandboxRepo.SHARED}),
    ]


def test_bare_harness_gates_apply_to_harness():
    """App(harness_merge_gates=[UserApproval()]) must gate /harness, not
    silently filter to an empty pipeline via the bare-gate APP default."""
    assert gates_for(_app([UserApproval()]), _project([]), SandboxRepo.HARNESS) == [
        UserApproval(repo=SandboxRepo.HARNESS),
    ]
