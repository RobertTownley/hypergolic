from pydantic import BaseModel, Field


class UnifiedSearchRequest(BaseModel):
    query: str
    mode: str = Field(default="all", description="'files', 'contents', 'all', or 'sessions'")
    respect_gitignore: bool = True
    include_hidden: bool = False
    max_file_results: int = 50
    max_session_results: int = 20
    project_id: str | None = None


class FileMatch(BaseModel):
    type: str = "file"
    path: str
    line: int | None = None
    text: str | None = None


class SessionMatch(BaseModel):
    type: str = "session"
    session_id: str
    project_id: str
    project_name: str
    model_tier: str
    created_at: str
    updated_at: str
    message_count: int
    match_text: str
    match_role: str
    first_message: str | None = None


class UnifiedSearchResponse(BaseModel):
    matches: list[FileMatch | SessionMatch]
