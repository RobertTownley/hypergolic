"""The injected environment and the registry that authorizes what comes back."""

import asyncio
import subprocess

import pytest

from hypergolic.sandbox import exec_env
from hypergolic.config.settings import settings
from hypergolic.sandbox.manager import docker


@pytest.fixture(autouse=True)
def _clean_registry():
    exec_env.EXEC_REGISTRY.clear()
    exec_env._SESSION_TOKENS.clear()
    exec_env._TOKEN_SESSIONS.clear()
    exec_env._IN_FLIGHT.clear()
    yield


def test_token_is_stable_within_a_session_and_unique_across_them():
    """There is no rotation within a session; teardown is the only lifecycle
    event."""
    assert exec_env.session_token("a") == exec_env.session_token("a")
    assert exec_env.session_token("a") != exec_env.session_token("b")


def test_token_resolves_to_its_session_and_nothing_else_does():
    token = exec_env.session_token("a")
    assert exec_env.resolve_token(token) == "a"
    assert exec_env.resolve_token("") is None
    assert exec_env.resolve_token(token + "x") is None


def test_discarding_a_token_makes_it_unusable():
    token = exec_env.session_token("a")
    exec_env.discard_session_token("a")
    assert exec_env.resolve_token(token) is None


def test_released_exec_id_is_no_longer_an_authorized_window():
    """A process that outlives its exec \u2014 a backgrounded dev server, a dormant
    dependency \u2014 must be refused rather than merely observed."""
    exec_id = exec_env.register_exec("s1", "gh pr list", container="dev")
    assert exec_env.lookup_exec(exec_id) is not None
    exec_env.release_exec(exec_id)
    assert exec_env.lookup_exec(exec_id) is None


def test_record_holds_the_full_originating_string():
    """The approval card reads the command from here, not from the shim, which
    only ever sees the fragment the shell forked it with."""
    exec_id = exec_env.register_exec(
        "s1", "analytics query x && rm -rf /tmp/probe", container="dev"
    )
    record = exec_env.lookup_exec(exec_id)
    assert record is not None
    assert record.command == "analytics query x && rm -rf /tmp/probe"
    assert record.session_id == "s1"
    assert record.container == "dev"


def test_concurrent_execs_each_hold_their_own_window():
    """Several tool calls in one turn run at once; the union of live keys is
    exactly the set of authorized callers."""
    first = exec_env.register_exec("s1", "one")
    second = exec_env.register_exec("s1", "two")
    assert first != second
    exec_env.release_exec(first)
    assert exec_env.lookup_exec(first) is None
    assert exec_env.lookup_exec(second) is not None


def test_suspension_nests_so_concurrent_invocations_do_not_unpause_each_other():
    exec_id = exec_env.register_exec("s1", "cmd")
    with exec_env.timeout_suspended(exec_id):
        with exec_env.timeout_suspended(exec_id):
            assert exec_env.is_timeout_suspended(exec_id)
        assert exec_env.is_timeout_suspended(exec_id)
    assert not exec_env.is_timeout_suspended(exec_id)


def test_suspension_is_a_noop_without_an_exec_id():
    with exec_env.timeout_suspended(None):
        assert not exec_env.is_timeout_suspended(None)


def test_exec_env_injects_only_broker_address_token_and_exec_id():
    """No other environment crosses the boundary: host commands see only what
    the harness process has."""
    flags = exec_env.exec_env("s1", "e1")
    keys = {value.split("=", 1)[0] for value in flags if value != "-e"}
    assert keys == {"HG_BROKER", "HG_TOKEN", "HG_EXEC_ID"}
    assert f"HG_TOKEN={exec_env.session_token('s1')}" in flags
    assert "HG_EXEC_ID=e1" in flags


def test_shims_win_on_path_without_discarding_the_image_s_own():
    """The collision rule depends on this precedence holding, which makes it a
    correctness requirement rather than a packaging detail — and replacing PATH
    outright would strip whatever a project's base image put there."""
    result = subprocess.run(
        ["sh", *exec_env.exec_argv('echo "$PATH"')[1:]],
        capture_output=True,
        text=True,
        env={"PATH": "/image/bin"},
        executable="/bin/sh",
    )
    assert result.stdout.strip() == f"{exec_env.TOOLS_BIN}:/image/bin"


def test_the_command_reaches_the_shell_exactly_as_written():
    """It travels as an argument, not interpolated into the prelude, so quoting
    and metacharacters mean what the agent meant."""
    command = 'echo "a && b" | tr a A'
    result = subprocess.run(
        ["sh", *exec_env.exec_argv(command)[1:]], capture_output=True, text=True
    )
    assert result.stdout == "A && b\n"
    assert command in exec_env.exec_argv(command)


def test_broker_address_follows_the_configured_port(monkeypatch):
    """One source of truth: a user override must not desync the shim from the
    server it is supposed to reach."""

    monkeypatch.setattr(settings, "HYPERGOLIC_PORT", 9999)
    assert exec_env.broker_address() == "host.docker.internal:9999"


@pytest.fixture
def fast_tick(monkeypatch):
    """Shrink the reaper's poll interval so a timeout is observable in a test."""

    monkeypatch.setattr(docker, "_TICK_SECONDS", 0.005)
    return docker


async def test_countdown_pauses_while_an_invocation_is_in_flight(fast_tick):
    """A shim blocked on the broker outlives the exec timeout, and reaping it
    would kill the chain mid-flight — worst case discarding a result a human
    just approved."""
    exec_id = exec_env.register_exec("s1", "gh pr create")
    finished = asyncio.Event()

    async def _proc():
        await finished.wait()
        return "done"

    async def _hold():
        # Stay in flight well past the deadline, then release and finish.
        with exec_env.timeout_suspended(exec_id):
            await asyncio.sleep(0.15)
        finished.set()

    task = asyncio.create_task(_hold())
    result = await fast_tick._wait_with_pause(
        asyncio.ensure_future(_proc()), timeout=0.03, suspend_key=exec_id
    )
    await task
    assert result == "done"


async def test_countdown_still_reaps_when_nothing_is_in_flight(fast_tick):
    with pytest.raises(asyncio.TimeoutError):
        await fast_tick._wait_with_pause(
            asyncio.ensure_future(asyncio.sleep(30)), timeout=0.03, suspend_key="absent"
        )


def _stateful(command, state_dir, restore_cwd=True, env=None):
    return subprocess.run(
        ["sh", *exec_env.exec_argv(command, persist_state=True, restore_cwd=restore_cwd)[1:]],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "HG_STATE_DIR": str(state_dir), **(env or {})},
    )


def test_stateful_prelude_persists_env_and_cwd_across_execs(tmp_path):
    """The whole point: an export or cd in one exec is live in the next."""
    _stateful(f"export FOO=bar; cd {tmp_path}", tmp_path)
    result = _stateful('echo "$FOO $PWD"', tmp_path)
    assert result.stdout.strip() == f"bar {tmp_path}"


def test_stateful_prelude_preserves_exit_code(tmp_path):
    """The snapshot write after eval must not launder the command's failure."""
    assert _stateful("exit 7", tmp_path).returncode == 7


def test_stateful_prelude_does_not_persist_per_exec_injections(tmp_path):
    """A stale HG_EXEC_ID from the snapshot would shadow the fresh one the next
    exec is authorized under; the broker would refuse it."""
    _stateful("true", tmp_path, env={"HG_EXEC_ID": "stale", "HG_TOKEN": "t", "HG_BROKER": "b"})
    snapshot = (tmp_path / ".hg_env").read_text()
    for name in ("HG_EXEC_ID", "HG_TOKEN", "HG_BROKER", "HG_STATE"):
        assert name not in snapshot


def test_stateful_prelude_does_not_accumulate_tools_bin_on_path(tmp_path):
    """PATH is persisted (agent edits should stick), so the prepend must be
    idempotent or every exec grows it by one shim dir."""
    _stateful("true", tmp_path)
    result = _stateful('echo "$PATH"', tmp_path)
    assert result.stdout.count(exec_env.TOOLS_BIN) == 1
    assert result.stdout.startswith(f"{exec_env.TOOLS_BIN}:")


def test_stateful_prelude_skips_cwd_restore_on_explicit_workdir(tmp_path):
    """`-w` means the agent chose a directory for this exec; the persisted cwd
    must not silently override it — but the exec still saves state."""
    sub = tmp_path / "sub"
    sub.mkdir()
    _stateful(f"cd {sub}", tmp_path)
    result = _stateful("pwd", tmp_path, restore_cwd=False)
    assert result.stdout.strip() != str(sub)
    assert _stateful("pwd", tmp_path).stdout.strip() == str(sub)
