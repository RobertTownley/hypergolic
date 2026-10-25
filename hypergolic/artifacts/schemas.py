from typing import Any

from pydantic import BaseModel


class ArtifactResponse(BaseModel):
    id: str
    session_id: str
    workflow_id: str
    state_id: str
    outcome: str
    artifact_id: str
    content: dict[str, Any]
    created_at: str
