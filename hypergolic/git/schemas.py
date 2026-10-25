from pydantic import BaseModel


class ChangedFile(BaseModel):
    path: str
    status: str
    staged: bool
    additions: int = 0
    deletions: int = 0


class GitStatusResponse(BaseModel):
    # session_id is stamped on the response so the frontend reducer can
    # route late-arriving responses back to the right per-session slot
    # in workspaceSlice.bySession. The field is populated by the router; the underlying
    # get_git_status / get_git_diff / … operations stay session-agnostic.
    session_id: str
    branch: str
    ahead: int
    behind: int
    staged: list[ChangedFile]
    unstaged: list[ChangedFile]
    untracked: list[str]
    # Every file differing from the session's base branch (committed branch
    # work + uncommitted edits). Populated only when the request carries a
    # base branch; empty in the plain status case. Backs the "All changes"
    # toggle in the Source Control panel.
    all_changes: list[ChangedFile] = []


class GitDiffResponse(BaseModel):
    session_id: str
    path: str = ""
    diff: str


class ReviewFile(BaseModel):
    path: str
    old_path: str | None = None
    status: str
    additions: int
    deletions: int
    patch: str


class GitChangesResponse(BaseModel):
    session_id: str
    files: list[ReviewFile]


class GitLogEntry(BaseModel):
    hash: str
    short_hash: str
    author: str
    date: str
    message: str
    refs: str


class GitLogResponse(BaseModel):
    session_id: str
    entries: list[GitLogEntry]


class MergeCandidate(BaseModel):
    parents: list[str]
    merged_from: str
    merged_count: int
    conflict_paths: list[str]
    view: str


class GitReviewResponse(BaseModel):
    session_id: str
    branch: str
    base_branch: str
    merge_base: str
    ahead: int
    behind: int
    commits: list[GitLogEntry]
    files: list[ReviewFile]
    merge: MergeCandidate | None = None


class GitCommitDetailResponse(BaseModel):
    session_id: str
    hash: str
    short_hash: str
    author: str
    date: str
    message: str
    diff: str


class GitBranchesResponse(BaseModel):
    session_id: str
    branches: list[str]
    current: str
