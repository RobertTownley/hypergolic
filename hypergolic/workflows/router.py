from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from hypergolic.harness.primitives.bundles import Workflow
from hypergolic.workflows.resolver import resolve_workflows
from hypergolic.workflows.schemas import PromptContentResponse

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _collect_prompt_paths(workflows: list[Workflow]) -> set[str]:
    paths: set[str] = set()
    for wf in workflows:
        if wf.prompt_path:
            paths.add(wf.prompt_path)
        for state in wf.states:
            if state.prompt_path:
                paths.add(state.prompt_path)
    return paths


@router.get("/prompt-content", response_model=PromptContentResponse)
def get_prompt_content(
    path: str = Query(..., description="Absolute path to prompt file"),
):
    workflows = resolve_workflows()
    allowed = _collect_prompt_paths(workflows)

    if path not in allowed:
        raise HTTPException(status_code=404, detail="Prompt path not found in any workflow")

    file_path = Path(path)
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="Prompt file not found on disk")

    return PromptContentResponse(path=path, content=file_path.read_text())
