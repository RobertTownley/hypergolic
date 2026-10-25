"""Low-level docker / docker compose subprocess runners."""

import asyncio
import codecs
import os
from typing import Awaitable, Callable, TypeVar

from hypergolic.sandbox.exec_env import is_timeout_suspended
from hypergolic.sandbox.manager.types import ExecResult, SandboxError, SandboxTimeout, SandboxUnavailableError

#: ``on_chunk(stream_name, text)`` — live output, decoded incrementally.
OnChunk = Callable[[str, str], Awaitable[None]]

_READ_CHUNK = 65536

_T = TypeVar("_T")

#: How often the reaper re-checks whether the clock is paused. Short enough that
#: a suspension entered just after a tick still lands well inside the timeout.
_TICK_SECONDS = 1.0


async def _drain(
    stream: asyncio.StreamReader, buf: bytearray, name: str, on_chunk: OnChunk | None
) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while chunk := await stream.read(_READ_CHUNK):
        buf += chunk
        if on_chunk and (text := decoder.decode(chunk)):
            await on_chunk(name, text)
    if on_chunk and (text := decoder.decode(b"", final=True)):
        await on_chunk(name, text)


async def _wait_with_pause(
    task: "asyncio.Future[_T]", timeout: float, suspend_key: str | None
) -> _T:
    """Await a task, pausing the countdown while a broker call is in flight.

    A shim blocked on the broker — waiting on a human, an OAuth round trip, or
    merely a slow host command — routinely outlives the exec timeout, and reaping
    it kills the whole chain mid-flight, worst case discarding the result of
    something a human just approved. So the clock stops for the lifetime of *any*
    in-flight invocation rather than only while an approval is pending: the
    auto-approved-but-slow case is the common one.
    """
    remaining = float(timeout)
    while True:
        try:
            return await asyncio.wait_for(
                asyncio.shield(task), timeout=min(remaining, _TICK_SECONDS)
            )
        except asyncio.TimeoutError:
            if is_timeout_suspended(suspend_key):
                continue
            remaining -= _TICK_SECONDS
            if remaining > 0:
                continue
            task.cancel()
            raise


async def _run_docker(
    *args: str,
    timeout: float = 60,
    env: dict[str, str] | None = None,
    suspend_key: str | None = None,
    on_chunk: OnChunk | None = None,
) -> ExecResult:
    """Run a docker command and return the result.

    ``suspend_key`` is the exec id whose in-flight broker invocations pause the
    timeout; see :func:`_wait_with_pause`. Output is read incrementally, so a
    timeout surfaces what was printed before the kill (``SandboxTimeout``) and
    ``on_chunk`` observes output live.
    """
    proc_env = {**os.environ, **env} if env else None
    proc = await asyncio.create_subprocess_exec(
        "docker", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=proc_env,
    )
    out, err = bytearray(), bytearray()
    assert proc.stdout is not None and proc.stderr is not None
    task = asyncio.ensure_future(asyncio.gather(
        _drain(proc.stdout, out, "stdout", on_chunk),
        _drain(proc.stderr, err, "stderr", on_chunk),
        proc.wait(),
    ))
    try:
        await _wait_with_pause(task, timeout, suspend_key)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise SandboxTimeout(
            f"Docker command timed out after {timeout}s: docker {' '.join(args)}",
            stdout=out.decode("utf-8", errors="replace"),
            stderr=err.decode("utf-8", errors="replace"),
        )

    return ExecResult(
        stdout=out.decode("utf-8", errors="replace"),
        stderr=err.decode("utf-8", errors="replace"),
        returncode=proc.returncode or 0,
    )


async def _run_compose(
    *args: str,
    project_name: str,
    config_path: str,
    timeout: int = 120,
    env: dict[str, str] | None = None,
    suspend_key: str | None = None,
    on_chunk: OnChunk | None = None,
) -> ExecResult:
    """Run a docker compose command."""
    full_args = [
        "compose",
        "-p", project_name,
        "-f", config_path,
        *args,
    ]
    return await _run_docker(
        *full_args, timeout=timeout, env=env, suspend_key=suspend_key,
        on_chunk=on_chunk,
    )


async def ensure_volume(name: str) -> None:
    """Create a named volume if it doesn't exist (idempotent)."""
    result = await _run_docker("volume", "create", name, timeout=15)
    if result.returncode != 0:
        raise SandboxError(
            f"Failed to create volume '{name}': {result.stderr.strip()}"
        )


async def ensure_docker_available() -> None:
    """Check that Docker is running. Raises SandboxUnavailableError if not."""
    try:
        result = await _run_docker("info", timeout=10)
    except FileNotFoundError:
        raise SandboxUnavailableError(
            "Docker CLI not found. Install Docker or ensure it's on your PATH."
        )
    except SandboxError:
        raise SandboxUnavailableError(
            "Docker is not responding. Start your container runtime "
            "and try again, or ask the user to start it."
        )
    if result.returncode != 0:
        raise SandboxUnavailableError(
            "Docker is not running. Start your container runtime "
            "and try again, or ask the user to start it.\n"
            f"Docker output: {result.stderr.strip()}"
        )
