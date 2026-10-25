from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hypergolic.git.actions import get_git_branches
from hypergolic.harness.app.state import get_app
from hypergolic.projects.operations import list_all_projects
from hypergolic.projects.schemas import ProjectResponse

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects():
    return list_all_projects()


class ProjectBranchesResponse(BaseModel):
    # Project-scoped variant of GitBranchesResponse used at pre-session
    # time (e.g. picking a base branch before creating the first session
    # for a project). The session-scoped /api/git/branches requires a
    # session_id, which doesn't exist yet at that point.
    project_id: str
    branches: list[str]
    current: str


@router.get("/{project_id}/branches", response_model=ProjectBranchesResponse)
def get_project_branches(project_id: str):
    try:
        project = get_app().get_project(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Project not found")
    data = get_git_branches(repo=Path(project.path))
    return ProjectBranchesResponse(
        project_id=project_id,
        branches=cast(list[str], data["branches"]),
        current=cast(str, data["current"]),
    )
