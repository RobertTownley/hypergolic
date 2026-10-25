from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from hypergolic.harness.primitives.results import InputSchema


class LandInput(InputSchema):
    sha: str = Field(description="The pushed commit (40-hex), as the update hook saw it")
    branch: str = Field(description="Host branch the push names (`refs/heads/<branch>`)")
    repo: Literal["app", "harness", "shared"] = Field(default="app")
    message: str = Field(
        default="",
        description="Squash message override (`git push -o message=...`); "
        "empty derives it from the branch's commit subjects",
    )
    description: str = Field(
        default="",
        description="What the merge does and why, shown to reviewers like a PR "
        "description (`git push -o description=...`, one option per line)",
    )
    mode: Literal["", "squash", "fast-forward"] = Field(
        default="",
        description="Land mode override (`git push -o mode=...`); empty uses "
        "the project's `land_mode`",
    )


class LandRejected(Exception):
    pass


@dataclass(frozen=True)
class Target:
    sha: str
    create: bool = False
    upstream: str | None = None
