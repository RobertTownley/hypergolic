import asyncio
import socket
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from hypergolic.mcptools import oauth
from hypergolic.mcptools.oauth import FileTokenStorage


def test_clear_removes_tokens_and_client_info(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(oauth, "TOKEN_DIR", tmp_path)
    storage = FileTokenStorage("srv")
    storage._tokens_path.write_text("{}")
    storage._client_info_path.write_text("{}")

    storage.clear()

    assert not storage._tokens_path.exists()
    assert not storage._client_info_path.exists()


def test_clear_is_idempotent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(oauth, "TOKEN_DIR", tmp_path)
    storage = FileTokenStorage("srv")

    storage.clear()
    storage.clear()



@pytest.fixture
def port(monkeypatch) -> int:
    with socket.socket() as probe:
        probe.bind(("localhost", 0))
        free = probe.getsockname()[1]
    monkeypatch.setattr(oauth, "OAUTH_CALLBACK_PORT", free)
    return free


@pytest.fixture
def opened(monkeypatch) -> list[str]:
    urls: list[str] = []
    monkeypatch.setattr(oauth.webbrowser, "open", urls.append)
    return urls


def _url(state: str) -> str:
    return f"https://auth.example/authorize?client_id=c&state={state}"


async def _callback(port: int, state: str, code: str = "the-code") -> tuple[int, str]:
    def get() -> tuple[int, str]:
        url = f"http://localhost:{port}/oauth/callback?code={code}&state={state}"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as err:
            return err.code, err.read().decode()

    return await asyncio.to_thread(get)


def _port_is_free(port: int) -> None:
    server = oauth._OAuthHTTPServer(("localhost", port), oauth._OAuthCallbackHandler)
    server.server_close()


async def test_a_busy_port_fails_before_any_browser_tab_opens(port, opened):
    """The incident: the retry opened a tab, then failed to bind; the user
    approved in a tab whose login was already dead."""
    with socket.socket() as squatter:
        squatter.bind(("localhost", port))
        squatter.listen()
        with pytest.raises(OSError):
            await oauth.OAuthLogin().open_browser(_url("s1"))
    assert opened == []


async def test_the_tab_says_successful_only_after_the_flow_finishes(port, opened):
    login = oauth.OAuthLogin()
    await login.open_browser(_url("s1"))
    assert opened == [_url("s1")]

    page = asyncio.create_task(_callback(port, "s1"))
    result = await login.wait_for_callback()
    assert (result.code, result.state) == ("the-code", "s1")
    await asyncio.sleep(0.05)
    assert not page.done()  # held open until the token exchange ends

    login.finish()
    status, body = await page
    assert status == 200 and "Authorization successful!" in body
    await asyncio.to_thread(login.join, 5)
    _port_is_free(port)


async def test_a_failed_exchange_shows_the_error_in_the_tab(port, opened):
    login = oauth.OAuthLogin()
    await login.open_browser(_url("s1"))
    page = asyncio.create_task(_callback(port, "s1"))
    await login.wait_for_callback()

    login.finish(RuntimeError("invalid_grant: code expired"))
    status, body = await page
    assert status == 400
    assert "Authorization failed" in body and "invalid_grant: code expired" in body
    assert "successful" not in body


async def test_a_tab_from_another_attempt_is_rejected_and_the_wait_goes_on(port, opened):
    login = oauth.OAuthLogin()
    await login.open_browser(_url("current"))
    waiting = asyncio.create_task(login.wait_for_callback())

    status, body = await _callback(port, "stale")
    assert status == 409 and "older login attempt" in body
    assert not waiting.done()

    page = asyncio.create_task(_callback(port, "current"))
    assert (await waiting).state == "current"
    login.finish()
    assert (await page)[0] == 200


async def test_a_cancelled_wait_frees_the_port(port, opened):
    """The callback port is fixed, so a wait that dies holding it fails every
    later login with "Address already in use"."""
    login = oauth.OAuthLogin()
    await login.open_browser(_url("s1"))
    waiting = asyncio.create_task(login.wait_for_callback())
    await asyncio.sleep(0)
    waiting.cancel()
    await asyncio.gather(waiting, return_exceptions=True)

    await asyncio.to_thread(login.join, 5)
    _port_is_free(port)


async def test_a_callback_the_flow_never_reports_on_is_released_when_closed(port, opened):
    login = oauth.OAuthLogin()
    await login.open_browser(_url("s1"))
    page = asyncio.create_task(_callback(port, "s1"))
    await login.wait_for_callback()

    login.close()
    status, body = await page
    assert status == 400 and "stopped this login" in body
    await asyncio.to_thread(login.join, 5)
    _port_is_free(port)
