from __future__ import annotations

import subprocess


class ContainerError(RuntimeError):
    pass


def docker(*args: str, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout
    )


def ensure_container(name: str, run_args: list[str]) -> None:
    state = docker("inspect", "-f", "{{.State.Running}}", name)
    if state.returncode != 0:
        result = docker(
            "run", "-d", "--name", name, "--restart", "unless-stopped", *run_args,
            timeout=300,
        )
    elif state.stdout.strip() != "true":
        result = docker("start", name)
    else:
        return
    if result.returncode != 0:
        raise ContainerError(f"Failed to start {name}: {result.stderr.strip()}")
