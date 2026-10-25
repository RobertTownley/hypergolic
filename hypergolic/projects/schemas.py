from pydantic import BaseModel


class ProjectResponse(BaseModel):
    id: str
    name: str
    path: str
    last_session_at: str | None = None
