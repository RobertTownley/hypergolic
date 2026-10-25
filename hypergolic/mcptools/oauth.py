import asyncio
import json
import logging
import threading
import webbrowser
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from html import escape
from urllib.parse import urlparse, parse_qs

from mcp.client.auth import TokenStorage
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthToken

from hypergolic.config.settings import INTERNALS_DIR

logger = logging.getLogger(__name__)

# Outside ~/.hypergolic so OAuth credentials are never exposed to project
# sandboxes via the read-only /harness mount.
TOKEN_DIR = INTERNALS_DIR / "tokens"
OAUTH_CALLBACK_PORT = 19836
OAUTH_REDIRECT_URI = f"http://localhost:{OAUTH_CALLBACK_PORT}/oauth/callback"


class FileTokenStorage(TokenStorage):
    def __init__(self, server_name: str) -> None:
        self._dir = TOKEN_DIR / server_name
        self._dir.mkdir(parents=True, exist_ok=True)
        self._tokens_path = self._dir / "tokens.json"
        self._client_info_path = self._dir / "client_info.json"

    async def get_tokens(self) -> OAuthToken | None:
        if not self._tokens_path.exists():
            return None
        try:
            data = json.loads(self._tokens_path.read_text())
            return OAuthToken.model_validate(data)
        except Exception:
            logger.warning("Failed to read tokens for MCP server", exc_info=True)
            return None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self._tokens_path.write_text(tokens.model_dump_json(indent=2))

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        if not self._client_info_path.exists():
            return None
        try:
            data = json.loads(self._client_info_path.read_text())
            return OAuthClientInformationFull.model_validate(data)
        except Exception:
            logger.warning("Failed to read client info for MCP server", exc_info=True)
            return None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self._client_info_path.write_text(client_info.model_dump_json(indent=2))

    def clear(self) -> None:
        """Wipe cached tokens + client registration so the next connect re-registers.

        Used to recover from servers that have rotated/dropped client registrations
        (returning `invalid_client` / "client_id is not registered").
        """
        for path in (self._tokens_path, self._client_info_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Failed to remove %s", path, exc_info=True)


CALLBACK_WAIT_SECONDS = 300
CALLBACK_POLL_SECONDS = 0.05
# How long the browser tab waits for the token exchange before it shows a
# "not confirmed" page. The exchange is one HTTP round trip.
OUTCOME_WAIT_SECONDS = 60


@dataclass
class _Round:
    """One authorization attempt: one browser tab, one listener, one state."""

    server: "_OAuthHTTPServer"
    expected_state: str | None
    received: threading.Event = field(default_factory=threading.Event)
    settled: threading.Event = field(default_factory=threading.Event)
    closed: threading.Event = field(default_factory=threading.Event)
    result: AuthorizationCodeResult | None = None
    error: str | None = None


class _OAuthHTTPServer(HTTPServer):
    timeout = 0.1  # handle_request returns this often so the serve loop can see `closed`
    round: _Round


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    server: _OAuthHTTPServer  # type: ignore[assignment]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/oauth/callback":
            self.send_response(404)
            self.end_headers()
            return
        rnd = self.server.round
        params = parse_qs(parsed.query)
        state = params.get("state", [None])[0]
        if rnd.expected_state is not None and state != rnd.expected_state:
            # A tab from another attempt. Reject it and keep waiting for ours.
            self._page(
                409,
                "Authorization not accepted",
                "This tab belongs to an older login attempt. Use the newest login "
                "tab, or run the activate again in Hypergolic.",
            )
            return
        if rnd.received.is_set():
            self._page(409, "Authorization already received", "You can close this tab.")
            return
        rnd.result = AuthorizationCodeResult(
            # A denied login has no code; "" makes the SDK fail the flow with
            # "No authorization code received", and the tab shows that.
            code=params.get("code", [""])[0],
            state=state,
            # RFC 9207: the SDK checks `iss` against the expected issuer.
            iss=params.get("iss", [None])[0],
        )
        rnd.received.set()
        # Answer only when the SDK has checked the code and exchanged it.
        if not rnd.settled.wait(OUTCOME_WAIT_SECONDS):
            self._page(
                504,
                "Authorization not confirmed",
                "Hypergolic did not confirm the login. Check the session.",
            )
        elif rnd.error is None:
            self._page(
                200,
                "Authorization successful!",
                "You can close this tab and return to Hypergolic.",
            )
        else:
            self._page(400, "Authorization failed", rnd.error)
        rnd.closed.set()

    def _page(self, status: int, title: str, detail: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(
            f"<html><body><h1>{escape(title)}</h1><p>{escape(detail)}</p></body></html>".encode()
        )

    def log_message(self, format: str, *args: object) -> None:
        pass


def _serve(server: _OAuthHTTPServer) -> None:
    # handle_request with a timeout, not serve_forever/handle_request(None): the
    # socket is closed here, by the thread that serves it. A socket closed while
    # another thread blocks on it stays bound, and the port is fixed.
    try:
        while not server.round.closed.is_set():
            server.handle_request()
    finally:
        server.server_close()


class OAuthLogin:
    """Browser login for one MCP server connection.

    The listener is bound before the browser opens, so a busy port fails the
    login before any tab appears. The tab's page reports the real outcome: it
    waits for `finish()` which the auth provider calls when the token exchange
    ends. A callback whose state belongs to another attempt is rejected.
    """

    def __init__(self) -> None:
        self._round: _Round | None = None
        self._thread: threading.Thread | None = None

    async def open_browser(self, authorization_url: str) -> None:
        self.close()
        state = parse_qs(urlparse(authorization_url).query).get("state", [None])[0]
        server = _OAuthHTTPServer(("localhost", OAUTH_CALLBACK_PORT), _OAuthCallbackHandler)
        rnd = _Round(server=server, expected_state=state)
        server.round = rnd
        self._round = rnd
        self._thread = threading.Thread(target=_serve, args=(server,), daemon=True)
        self._thread.start()
        logger.info("Opening browser for OAuth: %s", authorization_url)
        await asyncio.to_thread(webbrowser.open, authorization_url)

    async def wait_for_callback(self) -> AuthorizationCodeResult:
        rnd = self._round
        if rnd is None:
            raise RuntimeError("OAuth callback awaited before the browser was opened")
        try:
            for _ in range(int(CALLBACK_WAIT_SECONDS / CALLBACK_POLL_SECONDS)):
                if rnd.received.is_set():
                    break
                await asyncio.sleep(CALLBACK_POLL_SECONDS)
        except BaseException:
            self.close()
            raise
        if not rnd.received.is_set():
            self.close()
            raise TimeoutError("OAuth callback timed out")
        assert rnd.result is not None
        return rnd.result

    def finish(self, error: BaseException | None = None) -> None:
        """Report the outcome to the tab that is waiting; a no-op if none is."""
        rnd = self._round
        if rnd is None or not rnd.received.is_set() or rnd.settled.is_set():
            return
        if error is not None:
            rnd.error = str(error) or type(error).__name__
        rnd.settled.set()

    def close(self) -> None:
        rnd = self._round
        if rnd is None:
            return
        if not rnd.settled.is_set():
            rnd.error = rnd.error or "Hypergolic stopped this login."
            rnd.settled.set()
        rnd.closed.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the listener thread to release the port (tests)."""
        if self._thread is not None:
            self._thread.join(timeout)
