from pathlib import Path


from hypergolic.readiness.probes import (
    ProbeResult,
    detect_test_runners,
    render_scorecard,
    run_smoke_probes,
    run_static_probes,
)
from hypergolic.harness.project import Project
from hypergolic.sandbox.model.containers import Container
from hypergolic.sandbox.model.egress import Egress
from hypergolic.sandbox.model.sandbox import ProjectSandbox


def make_project(tmp_path: Path, **kwargs) -> Project:
    (tmp_path / ".git").mkdir(exist_ok=True)
    return Project(
        id="p", name="P", description="d", git_root=str(tmp_path), prompt="x", **kwargs
    )


def _static(project) -> dict[str, ProbeResult]:
    return {r.probe_id: r for r in run_static_probes(project)}


async def _smoke(project, sandbox, exec_fn) -> dict[str, ProbeResult]:
    return {r.probe_id: r for r in await run_smoke_probes(project, sandbox, exec_fn)}


def sandbox_two_containers() -> ProjectSandbox:
    return ProjectSandbox(
        id="sb",
        containers=[
            Container(id="dev", image="img"),
            Container(id="db", image="postgres", skip_workspace_mount=True),
        ],
    )


def sandbox_allow(hosts) -> ProjectSandbox:
    return ProjectSandbox(
        id="s", containers=[Container(id="dev", image="python:3.12")], egress=Egress.Allow(hosts)
    )


def test_static_probes_pass_for_healthy_project(tmp_path):
    by_id = _static(make_project(tmp_path))
    assert by_id["git-root"].passed is True
    assert by_id["prompt-paths"].passed is True
    assert by_id["sandbox-model"].passed is True  # default sandbox
    assert by_id["egress-policy"].detail.startswith("deny_all")


def test_static_probes_flag_bad_git_root_and_missing_prompt(tmp_path):
    project = Project(
        id="p",
        name="P",
        description="d",
        git_root=str(tmp_path / "nope"),
        prompt_path=str(tmp_path / "missing.md"),
    )
    by_id = _static(project)
    assert by_id["git-root"].passed is False and by_id["git-root"].fix
    assert by_id["prompt-paths"].passed is False


def test_static_probes_sandbox_opt_out_skips_smoke_material(tmp_path):
    project = make_project(tmp_path)
    project.configure_sandbox(None)
    by_id = _static(project)
    assert by_id["sandbox-model"].passed is None
    assert "egress-policy" not in by_id


def test_detect_test_runners(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (tmp_path / "package.json").write_text('{"scripts": {"test": "vitest"}}')
    names = {r.name for r in detect_test_runners(tmp_path)}
    assert names == {"pytest", "npm test"}
    assert detect_test_runners(tmp_path / "empty") == []


async def test_smoke_probes_happy_path(tmp_path):
    (tmp_path / "pyproject.toml").write_text("pytest\n")
    project = make_project(tmp_path)

    async def exec_fn(command: str, container: str):
        if "example.com" in command:
            return 7, ""  # blocked, as deny_all expects
        return 0, "ok"

    by_id = await _smoke(project, sandbox_two_containers(), exec_fn)
    assert by_id["exec[dev]"].passed and by_id["exec[db]"].passed
    assert by_id["workspace-rw[dev]"].passed and "workspace-rw[db]" not in by_id
    assert by_id["test-runner[pytest]"].passed
    assert by_id["egress-behavior"].passed  # blocked == declared


async def test_smoke_probes_dead_container_short_circuits(tmp_path):
    async def exec_fn(command: str, container: str):
        return (1, "boom") if container == "dev" else (0, "")

    by_id = await _smoke(make_project(tmp_path), sandbox_two_containers(), exec_fn)
    assert by_id["exec[dev]"].passed is False and by_id["exec[dev]"].fix
    assert "workspace-rw[dev]" not in by_id


async def test_egress_leak_detected(tmp_path):
    async def exec_fn(command: str, container: str):
        return 0, ""  # everything reachable

    by_id = await _smoke(make_project(tmp_path), sandbox_two_containers(), exec_fn)
    egress = by_id["egress-behavior"]
    assert egress.passed is False and "leak" in egress.fix.lower()


async def test_egress_probe_skips_without_curl(tmp_path):
    async def exec_fn(command: str, container: str):
        return (42, "NOTOOL") if "example.com" in command else (0, "")

    by_id = await _smoke(make_project(tmp_path), sandbox_two_containers(), exec_fn)
    assert by_id["egress-behavior"].passed is None


def test_render_scorecard_lists_fixes():
    results = [
        ProbeResult("a", "static", True, "fine"),
        ProbeResult("b", "smoke", False, "broken", fix="do X"),
        ProbeResult("c", "smoke", None, "skipped"),
    ]
    card = render_scorecard(results)
    assert "[PASS] a" in card and "[FAIL] b" in card and "[SKIP] c" in card
    assert "fix: do X" in card
    assert "1 failing" in card


async def test_egress_probe_allow_mode_reachable(tmp_path):
    async def exec_fn(command: str, container: str):
        return 0, ""

    by_id = await _smoke(make_project(tmp_path), sandbox_allow(["https://pypi.org"]), exec_fn)
    egress = by_id["egress-behavior"]
    assert egress.passed is True and "pypi.org" in egress.detail


async def test_egress_probe_allow_mode_unreachable_blames_proxy(tmp_path):
    async def exec_fn(command: str, container: str):
        return (7, "") if "pypi.org" in command else (0, "")

    by_id = await _smoke(make_project(tmp_path), sandbox_allow(["pypi.org"]), exec_fn)
    egress = by_id["egress-behavior"]
    assert egress.passed is False and "squid" in egress.fix


async def test_test_runner_missing_in_every_container(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")

    async def exec_fn(command: str, container: str):
        return (127, "not found") if "pytest" in command else (0, "")

    by_id = await _smoke(make_project(tmp_path), sandbox_two_containers(), exec_fn)
    runner = by_id["test-runner[pytest]"]
    assert runner.passed is False and "pytest" in runner.fix
