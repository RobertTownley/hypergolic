"""AWS SSO recovery (hypergolic.aws_sso).

Recovery from an expired IAM Identity Center session: botocore's silent
refresh is rejected past the org's max session duration, so the only fix is
an interactive `aws sso login`. These tests exercise the login runner, its
gating/throttling, and the pre-flight probe.
"""
import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from botocore.exceptions import TokenRetrievalError

from hypergolic import aws_sso
from hypergolic.aws_sso import (
    actionable_sso_error,
    attempt_sso_login,
    ensure_sso_session,
    sso_auth_errors,
)
from hypergolic import App, SsoConfig
from hypergolic.harness.app.state import app_context


@pytest.fixture(autouse=True)
def _fresh_throttles():
    aws_sso.reset_throttles()
    yield
    aws_sso.reset_throttles()


class _FakeProc:
    def __init__(self, returncode: int = 0, output: bytes = b"ok"):
        self.returncode = returncode
        self._output = output

    async def communicate(self):
        return self._output, None

    def kill(self):
        pass


def _token_error() -> TokenRetrievalError:
    return TokenRetrievalError(
        provider="sso", error_msg="Token has expired and refresh failed"
    )


def test_no_module_level_botocore_import():
    body = ast.parse(Path(aws_sso.__file__).read_text()).body
    imported = [node.module or "" for node in body if isinstance(node, ast.ImportFrom)]
    imported += [
        alias.name
        for node in body
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert not [name for name in imported if name.startswith("botocore")]


def test_sso_auth_errors_cover_token_retrieval():
    errors = sso_auth_errors()
    assert TokenRetrievalError in errors
    assert isinstance(_token_error(), errors)


async def test_attempt_sso_login_success_passes_profile():
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=0))
    with patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock):
        assert await attempt_sso_login("rr-nonprod") is True
    args = exec_mock.call_args.args
    assert args[:3] == ("aws", "sso", "login")
    assert ("--profile", "rr-nonprod") == args[3:5]


async def test_attempt_sso_login_no_profile_omits_flag():
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=0))
    with patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock):
        assert await attempt_sso_login(None) is True
    assert exec_mock.call_args.args == ("aws", "sso", "login")


async def test_attempt_sso_login_failure_returns_false():
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=1, output=b"denied"))
    with patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock):
        assert await attempt_sso_login("p") is False


async def test_attempt_sso_login_missing_cli_returns_false():
    exec_mock = AsyncMock(side_effect=FileNotFoundError("aws"))
    with patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock):
        assert await attempt_sso_login("p") is False


async def test_attempt_sso_login_throttles_repeat_attempts():
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=0))
    with patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock):
        assert await attempt_sso_login("p") is True
        # Second attempt inside the window: no subprocess, no browser tab.
        assert await attempt_sso_login("p") is False
    assert exec_mock.call_count == 1


async def test_attempt_sso_login_throttle_is_per_profile():
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=0))
    with patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock):
        assert await attempt_sso_login("a") is True
        assert await attempt_sso_login("b") is True
    assert exec_mock.call_count == 2


async def test_attempt_sso_login_gated_by_setting():
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=0))
    with (
        app_context(App(sso=SsoConfig(auto_login=False))),
        patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock),
    ):
        assert await attempt_sso_login("p") is False
    exec_mock.assert_not_called()


async def test_ensure_sso_session_logs_in_when_token_dead():
    login = AsyncMock(return_value=True)
    with (
        patch("hypergolic.aws_sso._probe_token", side_effect=_token_error()),
        patch("hypergolic.aws_sso.attempt_sso_login", login),
    ):
        assert await ensure_sso_session("p") is True
    login.assert_awaited_once_with("p")


async def test_ensure_sso_session_noop_when_token_fresh():
    login = AsyncMock()
    with (
        patch("hypergolic.aws_sso._probe_token", return_value=None),
        patch("hypergolic.aws_sso.attempt_sso_login", login),
    ):
        assert await ensure_sso_session("p") is False
    login.assert_not_called()


async def test_ensure_sso_session_swallows_unexpected_probe_errors():
    with patch("hypergolic.aws_sso._probe_token", side_effect=ValueError("boom")):
        assert await ensure_sso_session("p") is False


async def test_ensure_sso_session_throttles_probes():
    probe = patch("hypergolic.aws_sso._probe_token", return_value=None)
    with probe as probe_mock:
        await ensure_sso_session("p")
        await ensure_sso_session("p")
    assert probe_mock.call_count == 1


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now


async def test_failed_login_backs_off_then_allows_retry():
    clock = _Clock()
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=1, output=b"denied"))
    with (
        patch.object(aws_sso, "time", clock),
        patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock),
    ):
        assert await attempt_sso_login("p") is False
        # Inside the post-failure backoff window: no new subprocess.
        clock.now += aws_sso.LOGIN_THROTTLE_SECONDS + 1
        assert await attempt_sso_login("p") is False
        assert exec_mock.call_count == 1
        # Past the (doubled) backoff: one more attempt goes out.
        clock.now += aws_sso.LOGIN_THROTTLE_SECONDS * 2
        assert await attempt_sso_login("p") is False
        assert exec_mock.call_count == 2


async def test_login_gives_up_after_max_consecutive_failures():
    clock = _Clock()
    exec_mock = AsyncMock(return_value=_FakeProc(returncode=1, output=b"denied"))
    with (
        patch.object(aws_sso, "time", clock),
        patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock),
    ):
        for _ in range(SsoConfig().max_login_attempts):
            assert await attempt_sso_login("p") is False
            clock.now += 10_000
        assert aws_sso.login_attempts_exhausted("p")
        # Exhausted: no more MFA pushes no matter how much time passes.
        clock.now += 100_000
        assert await attempt_sso_login("p") is False
        assert exec_mock.call_count == SsoConfig().max_login_attempts
    msg = str(actionable_sso_error("p"))
    assert "gave up" in msg
    assert "aws sso login --profile p" in msg


async def test_successful_login_resets_failure_count():
    clock = _Clock()
    fail = _FakeProc(returncode=1, output=b"denied")
    ok = _FakeProc(returncode=0)
    exec_mock = AsyncMock(side_effect=[fail, ok])
    with (
        patch.object(aws_sso, "time", clock),
        patch("hypergolic.aws_sso.asyncio.create_subprocess_exec", exec_mock),
    ):
        assert await attempt_sso_login("p") is False
        clock.now += 10_000
        assert await attempt_sso_login("p") is True
    assert not aws_sso.login_attempts_exhausted("p")
    assert aws_sso._login_failures.get("p") is None


async def test_successful_probe_rearms_exhausted_login():
    aws_sso._login_failures["p"] = SsoConfig().max_login_attempts
    aws_sso._next_login_allowed["p"] = 10**12
    with patch("hypergolic.aws_sso._probe_token", return_value=None):
        assert await ensure_sso_session("p") is False
    assert not aws_sso.login_attempts_exhausted("p")
    assert aws_sso._next_login_allowed.get("p") is None


def test_actionable_error_names_the_profile():
    msg = str(actionable_sso_error("rr-nonprod"))
    assert "aws sso login --profile rr-nonprod" in msg
    assert "aws sso login`" in str(actionable_sso_error(None))
