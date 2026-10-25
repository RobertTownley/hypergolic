from fastapi import APIRouter, HTTPException, Query

from hypergolic.artifacts import artifact_rows
from hypergolic.artifacts.schemas import ArtifactResponse
from hypergolic.db.utils import to_iso_utc

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


def _response(row) -> ArtifactResponse:
    return ArtifactResponse(
        id=row.id,
        session_id=row.session_id,
        workflow_id=row.workflow_id,
        state_id=row.state_id,
        outcome=row.outcome,
        artifact_id=row.artifact_id,
        content=row.content,
        created_at=to_iso_utc(row.created_at),
    )


@router.get("", response_model=list[ArtifactResponse])
def list_artifacts(
    session_id: str | None = Query(None),
    workflow_id: str | None = Query(None),
    state_id: str | None = Query(None),
    outcome: str | None = Query(None),
    artifact_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    filters = dict(
        session_id=session_id, workflow_id=workflow_id, state_id=state_id,
        outcome=outcome, artifact_id=artifact_id,
    )
    rows = artifact_rows.find(
        newest_first=True, offset=offset, limit=limit,
        **{k: v for k, v in filters.items() if v},
    )
    return [_response(row) for row in rows]


@router.get("/{artifact_db_id}", response_model=ArtifactResponse)
def get_artifact(artifact_db_id: str):
    row = artifact_rows.get(artifact_db_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return _response(row)
