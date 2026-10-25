import asyncio
import logging
import re
from urllib.parse import parse_qs
from contextlib import asynccontextmanager, suppress
from importlib.metadata import version as pkg_version
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.types import ASGIApp, Receive, Scope, Send

from hypergolic.analytics.router import router as analytics_router
from hypergolic.config.settings import settings
from hypergolic.artifacts.router import router as artifacts_router
from hypergolic.commands.broker import router as broker_router
from hypergolic.attachments.router import router as attachments_router
from hypergolic.auth import readonly_session, redeem_bootstrap_token, verify_token
from hypergolic.docs.router import router as docs_router
from hypergolic.files.router import router as files_router
from hypergolic.files.harness_router import router as harness_files_router
from hypergolic.git.router import router as git_router
from hypergolic.harness.app.state import get_app
from hypergolic.mcptools.client.manager import get_mcp_manager
from hypergolic.mcptools.router import router as mcp_router
from hypergolic.projects.router import router as projects_router
from hypergolic.sandbox.manager.lifecycle import reconcile_sandbox_rows
from hypergolic.sandbox.manager.maintenance import run_startup_maintenance
from hypergolic.sandbox.manager.reap import bind_server_loop
from hypergolic.git.harness_repo import ensure_harness_repo
from hypergolic.sessions.recovery import recover_in_flight_sessions, recover_stranded_worktrees
from hypergolic.git.container_git import SandboxRepoUnavailable
from hypergolic.sessions.router import router as sessions_router
from hypergolic.system.loop_monitor import start_loop_lag_monitor
from hypergolic.system.router import router as system_router
from hypergolic.telemetry.router import router as telemetry_router
from hypergolic.telemetry.startup import launch_context
from hypergolic.telemetry.tracing import tracer
from hypergolic.websocket.router import router as websocket_router
from hypergolic.workflows.router import router as workflows_router
from hypergolic.search.router import router as search_router

logger = logging.getLogger(__name__)

AUTH_COOKIE = "h_token"


#: Paths where a segment right after the prefix addresses a session.
_SESSION_ADDRESSED = re.compile(r"^/api/(?:sessions|files/raw|mcp/sessions)/([^/?]+)")

#: Non-session literal segments that share those prefixes (fail closed: an
#: unlisted new literal route breaks spectators, not the scope).
_LITERAL_SEGMENTS = frozenset({"roles", "resolve"})

#: Never readable with a readonly token. /api/harness serves raw files under
#: ~/.hypergolic — including the DB holding every session's transcript.
_READONLY_DENIED_PREFIXES = ("/api/harness",)


def _readonly_scope_ok(path: str, query_string: bytes, session_id: str) -> bool:
    """May a token scoped to ``session_id`` read this request's target?

    Session-addressed paths and ``session_id`` query params must match the
    scope. Artifact reads must go through the list endpoint with the session
    filter — the by-id route ignores it. Everything else GET-reachable is
    metadata and stays readable so the SPA can render. Known trade-off: the
    session list exposes other sessions' descriptions (titles), not their
    content.
    """
    if path.startswith(_READONLY_DENIED_PREFIXES):
        return False
    m = _SESSION_ADDRESSED.match(path)
    if m and m.group(1) not in _LITERAL_SEGMENTS and m.group(1) != session_id:
        return False
    # keep_blank_values: Starlette resolves duplicate params to the last value,
    # so `?session_id=<scope>&session_id=` would pass an empty (unfiltered)
    # session_id to the endpoint while the scope check saw only the first.
    params = parse_qs(query_string.decode("utf-8", errors="replace"), keep_blank_values=True)
    if any(v != session_id for v in params.get("session_id", [])):
        return False
    if path.startswith("/api/artifacts") and (
        path != "/api/artifacts" or "session_id" not in params
    ):
        return False
    return True


def _is_protected(path: str) -> bool:
    if path == "/api/health":
        return False
    if path.startswith("/api/"):
        return True
    return False


class AuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and _is_protected(scope["path"]):
            request = Request(scope)
            token = request.cookies.get(AUTH_COOKIE, "")
            readonly_ok = False
            if scope["method"] in ("GET", "HEAD"):
                scoped_session = readonly_session(token)
                readonly_ok = scoped_session is not None and _readonly_scope_ok(
                    scope["path"], scope.get("query_string", b""), scoped_session
                )
            if not verify_token(token) and not readonly_ok:
                response = Response(content="Unauthorized", status_code=403)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


async def _startup_steps(app: FastAPI) -> None:
    with tracer.start_as_current_span("recover.in_flight_sessions"):
        await asyncio.to_thread(recover_in_flight_sessions)
    with tracer.start_as_current_span("recover.stranded_worktrees"):
        await asyncio.to_thread(recover_stranded_worktrees)
    # Installs that predate git-controlled harnesses get healed here; without a
    # repo there is no /harness mount and no harness merge path.
    with tracer.start_as_current_span("harness_repo.ensure"):
        await asyncio.to_thread(ensure_harness_repo)
    bind_server_loop(asyncio.get_running_loop())
    # Rows are reconciled with Docker reality before we serve traffic — a
    # resumed session must not exec against a "running" row whose containers
    # died with the old process. Surviving stacks stay up and are resumed.
    with tracer.start_as_current_span("sandbox.reconcile_rows"):
        await reconcile_sandbox_rows()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE:
        logger.warning(
            "HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE is set: all approval gates "
            "auto-approve and agents run unsandboxed on the host"
        )
    # Started before the startup span so its stall spans stay root traces.
    lag_monitor = start_loop_lag_monitor()
    with tracer.start_as_current_span("server.startup", context=launch_context()):
        await _startup_steps(app)
    # Reaping unknown stacks and warming images is backgrounded — a cold build
    # takes minutes and must not hold up the server; a session that starts
    # meanwhile just builds on the way in.
    maintenance = asyncio.create_task(
        run_startup_maintenance(
            [s for p in get_app().projects if (s := p.resolved_sandbox) is not None]
        )
    )
    yield
    bind_server_loop(None)
    maintenance.cancel()
    with suppress(asyncio.CancelledError):
        await maintenance
    lag_monitor.cancel()
    with suppress(asyncio.CancelledError):
        await lag_monitor
    await get_mcp_manager().shutdown()


app = FastAPI(
    title="Hypergolic API",
    description="API for conversing with the Hypergolic agent.",
    version=pkg_version("hypergolic"),
    lifespan=lifespan,
)

app.add_middleware(AuthMiddleware)  # type: ignore[arg-type]
FastAPIInstrumentor.instrument_app(app, excluded_urls="/ws$,/api/health$")


@app.exception_handler(SandboxRepoUnavailable)
async def _sandbox_repo_unavailable(request, exc: SandboxRepoUnavailable) -> JSONResponse:
    """Sandbox-owned repos only answer while their container runs: say so."""
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/api/health")
async def health_check() -> JSONResponse:
    """Health check endpoint for server readiness."""
    return JSONResponse({"status": "ok"})


# Not under /api, so the browser-facing cookie middleware never applies: the
# broker carries its own per-session bearer token and must not accept the UI's.
app.include_router(broker_router)
app.include_router(projects_router)
app.include_router(sessions_router)
app.include_router(attachments_router)
app.include_router(files_router)
app.include_router(harness_files_router)
app.include_router(git_router)
app.include_router(mcp_router)
app.include_router(websocket_router)
app.include_router(analytics_router)
app.include_router(docs_router)
app.include_router(artifacts_router)
app.include_router(search_router)
app.include_router(workflows_router)
app.include_router(system_router)
app.include_router(telemetry_router)

_UI_DIST = Path(__file__).resolve().parent / "ui_dist"


def _serve_index(bootstrap_token: str | None = None) -> Response:
    html = (_UI_DIST / "index.html").read_text()
    response = HTMLResponse(html)
    if bootstrap_token:
        session_token = redeem_bootstrap_token(bootstrap_token)
        if session_token:
            response.set_cookie(
                AUTH_COOKIE,
                session_token,
                httponly=True,
                samesite="strict",
                path="/",
            )
    return response


# The UI is built into ui_dist/assets/ by `pnpm build`. In fresh worktrees
# and CI checkouts that directory may not exist yet; mounting StaticFiles on
# a missing dir raises at import time, which breaks every test that loads
# the API module. Mount only if the build output is present — the SPA
# fallback route below still works for any route the agent hits in tests.
_UI_ASSETS = _UI_DIST / "assets"
if _UI_ASSETS.is_dir():
    app.mount("/assets", StaticFiles(directory=_UI_ASSETS), name="ui-assets")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str = "", token: str = Query(default="")):
    if full_path:
        file_path = (_UI_DIST / full_path).resolve()
        try:
            file_path.relative_to(_UI_DIST.resolve())
        except ValueError:
            return _serve_index(bootstrap_token=token)
        if file_path.is_file():
            return FileResponse(file_path)
    return _serve_index(bootstrap_token=token)
