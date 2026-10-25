import asyncio
import json
import logging
import mimetypes
from pathlib import Path
from urllib.parse import quote

from watchfiles import Change, awatch

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from hypergolic.files.search import search_file_contents, search_file_names
from hypergolic.files.tree import build_file_tree, get_repo_root
from hypergolic.files.schemas import FileNode, FileSearchRequest, FileSearchMatch, FileSearchResponse
from hypergolic.files.language import detect_language
from hypergolic.sessions.repo_resolver import resolve_project_sandbox, resolve_repo_path
from hypergolic.files import sandbox_browser
from hypergolic.sandbox.manager.types import SandboxError, SandboxNotReadyError

logger = logging.getLogger(__name__)

# 503, not 409: the client should say "starting" and retry, not report failure.
SANDBOX_STARTING_DETAIL = "Sandbox is starting up."

router = APIRouter(prefix="/api/files", tags=["files"])


class FileTreeResponse(BaseModel):
    # See hypergolic/git/schemas.py for the rationale — session_id is
    # stamped on scoped responses so the frontend reducer can route
    # late-arriving responses to the right per-session cache slot.
    session_id: str
    root: str
    tree: list[FileNode]


class FileContentResponse(BaseModel):
    session_id: str
    path: str
    content: str
    language: str


@router.get("/tree", response_model=FileTreeResponse)
def get_file_tree(session_id: str):
    repo = resolve_repo_path(session_id)
    return FileTreeResponse(
        session_id=session_id,
        root=get_repo_root(repo),
        tree=build_file_tree(repo),
    )


def resolve_within(root: Path, path: str) -> Path:
    file_path = (root / path).resolve()
    try:
        file_path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return file_path


def read_file_response(root: Path, path: str, session_id: str) -> FileContentResponse:
    file_path = resolve_within(root, path)
    rel_path = str(file_path.relative_to(root))
    try:
        content = file_path.read_text(errors="replace")
    except Exception as e:
        logger.error("Error reading file %s", path, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    return FileContentResponse(
        session_id=session_id,
        path=rel_path,
        content=content,
        language=detect_language(rel_path),
    )


def _repo_root(session_id: str) -> Path:
    return Path(get_repo_root(resolve_repo_path(session_id))).resolve()


@router.get("/read", response_model=FileContentResponse)
def read_file_content(path: str, session_id: str):
    return read_file_response(_repo_root(session_id), path, session_id)


def _resolve_within_repo(session_id: str, path: str) -> tuple[Path, Path]:
    repo_root = _repo_root(session_id)
    return repo_root, resolve_within(repo_root, path)


@router.get("/raw/resolve")
def resolve_raw_path(path: str, session_id: str):
    # Accepts absolute or repo-relative paths (e.g. from file:// links in
    # chat) and redirects to the canonical /raw URL so relative assets in
    # served HTML resolve correctly.
    repo_root, file_path = _resolve_within_repo(session_id, path)
    rel_path = file_path.relative_to(repo_root)
    return RedirectResponse(f"/api/files/raw/{session_id}/{quote(str(rel_path))}")


@router.get("/raw/{session_id}/{path:path}")
def serve_raw_file(session_id: str, path: str):
    _, file_path = _resolve_within_repo(session_id, path)
    media_type = mimetypes.guess_type(file_path.name)[0] or "text/plain"
    return FileResponse(file_path, media_type=media_type)


@router.post("/search", response_model=FileSearchResponse)
def search_files(req: FileSearchRequest, session_id: str):
    repo = resolve_repo_path(session_id)
    repo_root = Path(get_repo_root(repo))

    if not req.query.strip():
        return FileSearchResponse(session_id=session_id, matches=[])

    matches: list[FileSearchMatch] = []

    if req.mode in ("files", "all"):
        matches.extend(search_file_names(
            req.query, repo_root, req.respect_gitignore, req.include_hidden, req.max_results,
        ))

    if req.mode in ("contents", "all"):
        content_limit = req.max_results - len(matches) if req.mode == "all" else req.max_results
        if content_limit > 0:
            matches.extend(search_file_contents(
                req.query, repo_root, req.respect_gitignore, req.include_hidden, content_limit,
            ))

    return FileSearchResponse(session_id=session_id, matches=matches[:req.max_results])


@router.get("/sandbox/containers", response_model=sandbox_browser.SandboxContainersResponse)
def get_sandbox_containers(session_id: str):
    sandbox = resolve_project_sandbox(session_id)
    return sandbox_browser.list_containers(session_id, sandbox)


@router.get("/sandbox/tree", response_model=sandbox_browser.SandboxTreeResponse)
async def get_sandbox_tree(session_id: str, container: str, root: str, path: str | None = None):
    project_root = str(await asyncio.to_thread(resolve_repo_path, session_id))
    try:
        return await sandbox_browser.list_directory(
            session_id, container, root, path, project_root
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SandboxNotReadyError:
        raise HTTPException(status_code=503, detail=SANDBOX_STARTING_DETAIL)
    except SandboxError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/sandbox/read", response_model=sandbox_browser.SandboxContentResponse)
async def read_sandbox_file(session_id: str, container: str, root: str, path: str):
    project_root = str(await asyncio.to_thread(resolve_repo_path, session_id))
    try:
        return await sandbox_browser.read_file(
            session_id, container, root, path, project_root
        )
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="Path is a directory")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SandboxNotReadyError:
        raise HTTPException(status_code=503, detail=SANDBOX_STARTING_DETAIL)
    except SandboxError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/watch")
async def watch_files_sse(session_id: str):
    # SSE stream: the session_id is echoed in the 'connected' frame so the
    # client can confirm the scope matches what it requested; subsequent
    # 'changes' frames don't carry it (they're delivered to the already-
    # scoped connection).
    repo = await asyncio.to_thread(resolve_repo_path, session_id)

    async def event_stream():
        repo_root = get_repo_root(repo)
        yield f"data: {json.dumps({'type': 'connected', 'session_id': session_id, 'root': repo_root})}\n\n"

        try:
            async for changes in awatch(repo_root):
                changed_paths = [
                    {
                        "change": "added" if c == Change.added else "modified" if c == Change.modified else "deleted",
                        "path": str(Path(p).relative_to(repo_root)),
                    }
                    for c, p in changes
                ]
                yield f"data: {json.dumps({'type': 'changes', 'changes': changed_paths})}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
