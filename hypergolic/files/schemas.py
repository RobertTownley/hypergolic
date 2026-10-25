from pydantic import BaseModel, Field


class FileNode(BaseModel):
    name: str
    path: str
    is_dir: bool
    git_status: str | None = None
    children: list["FileNode"] | None = None


class FileSearchMatch(BaseModel):
    path: str
    line: int | None = None
    text: str | None = None


class FileSearchRequest(BaseModel):
    query: str
    mode: str = Field(default="files", description="'files', 'contents', or 'all'")
    respect_gitignore: bool = True
    include_hidden: bool = False
    max_results: int = 50


class FileSearchResponse(BaseModel):
    # session_id echoed for scope-addressed file search endpoints. The
    # cross-project FileFinder uses a different router (hypergolic/search/)
    # that doesn't carry session scope — this field is for the
    # session-scoped /api/files/search endpoint.
    session_id: str = ""
    matches: list[FileSearchMatch]
