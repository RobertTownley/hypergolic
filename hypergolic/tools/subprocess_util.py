import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast


def has_ripgrep() -> bool:
    return shutil.which("rg") is not None


def _strip_own_virtual_env(env: dict[str, str]) -> dict[str, str]:
    """Drop VIRTUAL_ENV if it points to Hypergolic's own venv.

    Child processes like ``uv run`` in a user's project warn when an
    inherited ``VIRTUAL_ENV`` doesn't match the project's ``.venv``. If the
    value is Hypergolic's own venv (i.e. merely inherited), strip it so the
    child tool can resolve its own environment cleanly. A deliberately
    different ``VIRTUAL_ENV`` set by the caller is left untouched.
    """
    venv = env.get("VIRTUAL_ENV")
    if venv and Path(venv) == Path(sys.prefix):
        env = {k: v for k, v in env.items() if k != "VIRTUAL_ENV"}
    return env


def load_env_file(path: str | Path) -> dict[str, str]:
    env: dict[str, str] = {}
    filepath = Path(path)
    if not filepath.is_file():
        return env
    for line in filepath.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
    return env


def _build_env(
    env_file: str | Path | None,
    env_overrides: dict[str, str] | None,
    cwd: str | Path | None,
    existing_env: dict[str, str] | None,
) -> dict[str, str] | None:
    if env_file is None and env_overrides is None and existing_env is None:
        return None

    env = existing_env if existing_env is not None else os.environ.copy()

    if env_file is not None:
        env_path = Path(env_file)
        if not env_path.is_absolute() and cwd is not None:
            env_path = Path(cwd) / env_path
        env.update(load_env_file(env_path))

    if env_overrides is not None:
        env.update(env_overrides)

    return _strip_own_virtual_env(env)


async def run_subprocess(
    *args: Any,
    env_file: str | Path | None = None,
    env_overrides: dict[str, str] | None = None,
    **kwargs: Any,
) -> subprocess.CompletedProcess[str]:
    kwargs.setdefault("capture_output", True)
    kwargs.setdefault("text", True)

    built_env = _build_env(
        env_file=env_file,
        env_overrides=env_overrides,
        cwd=kwargs.get("cwd"),
        existing_env=kwargs.get("env"),
    )
    if built_env is not None:
        kwargs["env"] = built_env
    elif "VIRTUAL_ENV" in os.environ:
        # No explicit env given; still strip our own VIRTUAL_ENV so it doesn't
        # leak into child tools like `uv run` in user projects.
        kwargs["env"] = _strip_own_virtual_env(os.environ.copy())

    result = await asyncio.to_thread(subprocess.run, *args, **kwargs)
    return cast(subprocess.CompletedProcess[str], result)


def format_exec_output(stdout: str, stderr: str, returncode: int) -> str:
    if returncode == 0:
        return "\n".join(p for p in (stdout, stderr) if p) or "(no output)"
    parts = [stdout] if stdout else []
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    parts.append(f"[exit {returncode}]")
    return "\n".join(parts)
