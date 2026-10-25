"""Tiered project-readiness probes.

Two cheap tiers below a full simulated session:

- **static** — in-process config checks: paths exist, the sandbox model
  compiles, egress policy is coherent. Free, instant.
- **smoke** — real ``docker compose`` exec probes against the project's
  sandbox: containers start, /app is writable, git and detected test runners
  are present, egress behaves as the policy declares. No LLM cost.

Escalation to tier three (a conducted simulated session) is a
judgement call the harness-checkup skill makes with the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Literal

from hypergolic.sandbox.compose import compile_compose
from hypergolic.harness.project import Project
from hypergolic.sandbox.model.egress import EgressMode
from hypergolic.sandbox.model.sandbox import ProjectSandbox

Tier = Literal["static", "smoke"]

# exec_fn(command, container) -> (returncode, stdout+stderr)
ExecFn = Callable[[str, str], Awaitable[tuple[int, str]]]


@dataclass
class ProbeResult:
    probe_id: str
    tier: Tier
    passed: bool | None  # None = skipped / informational
    detail: str
    fix: str = ""


@dataclass
class TestRunner:
    """A test framework detected in the repo and the command proving a container can run it."""

    name: str
    check_command: str


def detect_test_runners(root: Path) -> list[TestRunner]:
    runners: list[TestRunner] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file() and "pytest" in pyproject.read_text(errors="ignore"):
        runners.append(TestRunner("pytest", "python -m pytest --version"))
    package_json = root / "package.json"
    if package_json.is_file() and re.search(r'"test"\s*:', package_json.read_text(errors="ignore")):
        runners.append(TestRunner("npm test", "node --version"))
    if (root / "go.mod").is_file():
        runners.append(TestRunner("go test", "go version"))
    if (root / "Cargo.toml").is_file():
        runners.append(TestRunner("cargo test", "cargo --version"))
    return runners


def run_static_probes(project: Project) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    root = Path(project.git_root).expanduser()

    if root.is_dir() and (root / ".git").exists():
        results.append(ProbeResult("git-root", "static", True, str(root)))
    else:
        results.append(
            ProbeResult(
                "git-root",
                "static",
                False,
                f"{root} missing or not a git repo",
                fix=f"Fix git_root in the Project('{project.id}', ...) registration",
            )
        )

    missing = [
        p
        for p in [project.prompt_path, *(s.prompt_path for s in project.skills)]
        if p and not Path(p).expanduser().is_file()
    ]
    if missing:
        results.append(
            ProbeResult(
                "prompt-paths",
                "static",
                False,
                f"missing: {', '.join(missing)}",
                fix="Create the prompt file(s) or correct prompt_path",
            )
        )
    else:
        results.append(ProbeResult("prompt-paths", "static", True, "all prompt files present"))

    sandbox = project.resolved_sandbox
    if sandbox is None:
        results.append(
            ProbeResult(
                "sandbox-model",
                "static",
                None,
                "project opted out of sandbox (no cmd tool); smoke tier n/a",
            )
        )
        return results

    try:
        compile_compose(sandbox)
        results.append(
            ProbeResult(
                "sandbox-model",
                "static",
                True,
                f"'{sandbox.id}': {len(sandbox.containers)} container(s) compile to compose",
            )
        )
    except Exception as e:  # pragma: no cover - model validates on construction
        results.append(
            ProbeResult(
                "sandbox-model",
                "static",
                False,
                str(e),
                fix="Fix the ProjectSandbox model passed to configure_sandbox",
            )
        )

    egress = sandbox.egress
    if egress.mode is EgressMode.DENY_ALL:
        detail = "deny_all: runtime package installs will fail; bake deps into container images"
    elif egress.mode is EgressMode.ALLOW:
        detail = f"allowlist: {', '.join(sorted(egress.hosts))}"
    else:
        detail = "allow_all: no egress boundary"
    results.append(ProbeResult("egress-policy", "static", True, detail))

    skipped = [c.id for c in sandbox.containers if c.skip_workspace_mount]
    if skipped:
        results.append(
            ProbeResult(
                "workspace-coverage",
                "static",
                None,
                f"no /app mount (by design?): {', '.join(skipped)}",
            )
        )

    runners = detect_test_runners(root)
    results.append(
        ProbeResult(
            "test-manifests",
            "static",
            True if runners else None,
            ", ".join(r.name for r in runners) if runners else "no test framework detected in repo",
            fix="" if runners else "If the project has tests, add a manifest agents can discover",
        )
    )
    return results


async def run_smoke_probes(
    project: Project,
    sandbox: ProjectSandbox,
    exec_fn: ExecFn,
) -> list[ProbeResult]:
    """Exec probes inside each sandbox container via ``exec_fn``.

    ``exec_fn`` is injected so callers own the manager plumbing and tests can
    fake it.
    """
    results: list[ProbeResult] = []
    mounted = [c.id for c in sandbox.containers if not c.skip_workspace_mount]

    async def check(probe_id: str, container: str, command: str, fix: str) -> bool:
        try:
            code, output = await exec_fn(command, container)
        except Exception as e:
            results.append(ProbeResult(probe_id, "smoke", False, f"{container}: {e}", fix=fix))
            return False
        if code == 0:
            results.append(ProbeResult(probe_id, "smoke", True, f"{container}: ok"))
            return True
        results.append(
            ProbeResult(
                probe_id, "smoke", False, f"{container}: exit {code}: {output.strip()[:200]}", fix=fix
            )
        )
        return False

    for cid in sandbox.container_ids:
        alive = await check(
            f"exec[{cid}]",
            cid,
            "true",
            "Container won't exec: check its image/entrypoint and `docker compose logs`",
        )
        if not alive:
            continue
        if cid in mounted:
            await check(
                f"workspace-rw[{cid}]",
                cid,
                "touch /app/.hg_probe && rm /app/.hg_probe",
                "Workspace mount broken or read-only: verify HYPERGOLIC_WORKSPACE bind mount",
            )
            await check(
                f"git[{cid}]",
                cid,
                "git --version",
                f"Install git in the '{cid}' image (agents need it for diffs/blame)",
            )

    runners = detect_test_runners(Path(project.git_root).expanduser())
    for runner in runners:
        found = False
        detail_parts = []
        for cid in mounted:
            try:
                code, output = await exec_fn(runner.check_command, cid)
            except Exception as e:
                detail_parts.append(f"{cid}: {e}")
                continue
            if code == 0:
                found = True
                detail_parts.append(f"{cid}: {output.strip().splitlines()[0] if output.strip() else 'ok'}")
                break
            detail_parts.append(f"{cid}: exit {code}")
        results.append(
            ProbeResult(
                f"test-runner[{runner.name}]",
                "smoke",
                found,
                "; ".join(detail_parts) or "no workspace-mounted containers",
                fix="" if found else f"Add the {runner.name} toolchain to a sandbox container image",
            )
        )

    if mounted:
        results.append(await _egress_probe(sandbox, mounted[0], exec_fn))
    return results


async def _egress_probe(sandbox: ProjectSandbox, container: str, exec_fn: ExecFn) -> ProbeResult:
    mode = sandbox.egress.mode
    if mode is EgressMode.ALLOW and sandbox.egress.hosts:
        target = sandbox.egress.domain(sandbox.egress.hosts[0])
        expect_reachable = True
    else:
        target = "example.com"
        expect_reachable = mode is EgressMode.ALLOW_ALL

    fetch = (
        f"if command -v curl >/dev/null; then curl -m 6 -so /dev/null https://{target}; "
        f"elif command -v wget >/dev/null; then timeout 6 wget -qO /dev/null https://{target}; "
        "else echo NOTOOL; exit 42; fi"
    )
    try:
        code, output = await exec_fn(fetch, container)
    except Exception as e:
        return ProbeResult("egress-behavior", "smoke", False, f"{container}: {e}")
    if code == 42 and "NOTOOL" in output:
        return ProbeResult(
            "egress-behavior", "smoke", None, f"{container}: no curl/wget to probe with; skipped"
        )
    reachable = code == 0
    if reachable == expect_reachable:
        return ProbeResult(
            "egress-behavior",
            "smoke",
            True,
            f"{target} {'reachable' if reachable else 'blocked'} as policy declares ({mode.value})",
        )
    if expect_reachable:
        return ProbeResult(
            "egress-behavior",
            "smoke",
            False,
            f"{target} unreachable despite {mode.value} policy",
            fix="Check the egress proxy container is healthy (squid) and the host is spelled right",
        )
    return ProbeResult(
        "egress-behavior",
        "smoke",
        False,
        f"{target} reachable despite deny_all",
        fix="Egress boundary leak: verify the compose networks include the internal-only network",
    )


def render_scorecard(results: list[ProbeResult]) -> str:
    lines = ["# Readiness scorecard", ""]
    for tier in ("static", "smoke"):
        tier_results = [r for r in results if r.tier == tier]
        if not tier_results:
            continue
        passed = sum(1 for r in tier_results if r.passed is True)
        graded = sum(1 for r in tier_results if r.passed is not None)
        lines.append(f"## {tier} — {passed}/{graded} passed")
        for r in tier_results:
            mark = "PASS" if r.passed else ("SKIP" if r.passed is None else "FAIL")
            lines.append(f"- [{mark}] {r.probe_id}: {r.detail}")
            if r.fix and r.passed is False:
                lines.append(f"      fix: {r.fix}")
        lines.append("")
    failures = [r for r in results if r.passed is False]
    lines.append(
        "All probes green."
        if not failures
        else f"{len(failures)} failing probe(s) — fixes listed above."
    )
    return "\n".join(lines)
