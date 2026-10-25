from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from hypergolic.enums import ModelTier


WorktreeStatus = Literal[
    "pending", "creating", "starting_sandbox", "cloning", "seeding", "ready",
    "create_failed", "seed_failed",
]


class Session(BaseModel):
    id: str
    model_tier: ModelTier
    project_id: str
    project_path: str
    role: str = "generalist"
    parent_id: str | None = None
    dispatch_prompt: str | None = None
    conducted_by: str | None = None
    origin: str | None = None
    worktree_path: str
    base_branch: str
    # None after conclusion: a null branch means "already merged/discarded"
    # (merge-candidate discovery keys on it); a null status marks the
    # worktree itself concluded/torn down.
    worktree_branch: str | None = None
    worktree_status: WorktreeStatus | None = None
    repo_pins: dict[str, str] = {}

    def working_directory(self) -> Path:
        return Path(self.worktree_path)

    def live_branch(self) -> str:
        """The worktree branch, which live sessions always have.

        Raises if the branch was already merged/discarded (concluded session).
        """
        if self.worktree_branch is None:
            raise RuntimeError(f"Session {self.id} has no live worktree branch")
        return self.worktree_branch
