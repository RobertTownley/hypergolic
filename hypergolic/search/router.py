from pathlib import Path

from fastapi import APIRouter, HTTPException

from hypergolic.files.search import search_file_contents, search_file_names
from hypergolic.files.tree import get_repo_root
from hypergolic.search.schemas import FileMatch, SessionMatch, UnifiedSearchRequest, UnifiedSearchResponse
from hypergolic.sessions.search import search_sessions
from hypergolic.harness.app.state import get_app

router = APIRouter(prefix="/api/search", tags=["search"])


def _resolve_project_path(project_id: str | None) -> Path | None:
    if not project_id:
        return None

    try:
        return Path(get_app().get_project(project_id).path)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found") from None


@router.post("", response_model=UnifiedSearchResponse)
def unified_search(req: UnifiedSearchRequest):
    if not req.query.strip():
        return UnifiedSearchResponse(matches=[])

    matches: list[FileMatch | SessionMatch] = []

    # File matches (for modes: files, contents, all)
    if req.mode != "sessions":
        repo = _resolve_project_path(req.project_id)
        repo_root = Path(get_repo_root(repo))

        if req.mode in ("files", "all"):
            file_matches = search_file_names(
                req.query, repo_root, req.respect_gitignore, req.include_hidden, req.max_file_results,
            )
            matches.extend(FileMatch(path=m.path, line=m.line, text=m.text) for m in file_matches)

        if req.mode in ("contents", "all"):
            content_limit = req.max_file_results - len(matches) if req.mode == "all" else req.max_file_results
            if content_limit > 0:
                content_matches = search_file_contents(
                    req.query, repo_root, req.respect_gitignore, req.include_hidden, content_limit,
                )
                matches.extend(FileMatch(path=m.path, line=m.line, text=m.text) for m in content_matches)

    # Session matches (for modes: sessions, all)
    if req.mode in ("sessions", "all"):
        session_matches = search_sessions(req.query, req.project_id, req.max_session_results)
        matches.extend(
            SessionMatch(
                session_id=m.session_id,
                project_id=m.project_id,
                project_name=m.project_name,
                model_tier=m.model_tier,
                created_at=m.created_at,
                updated_at=m.updated_at,
                message_count=m.message_count,
                match_text=m.match_text,
                match_role=m.match_role,
                first_message=m.first_message,
            )
            for m in session_matches
        )

    return UnifiedSearchResponse(matches=matches)
