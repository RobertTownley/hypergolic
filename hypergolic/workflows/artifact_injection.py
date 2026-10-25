from __future__ import annotations

import asyncio
import logging

from anthropic.types import MessageParam, TextBlockParam

from hypergolic.messages.persistence import persist_messages
from hypergolic.messages.types import (
    ARTIFACT_MESSAGE_PREFIX,
    BroadcastEvent,
    BroadcastFn,
)
from hypergolic.schemas import Session
from hypergolic.workflows.rendering import render_artifact_text

from hypergolic.artifacts import artifact_rows


def load_artifacts(
    session_id: str,
    artifact_ids: list[str],
) -> list[tuple[str, dict, str]]:
    return [
        (row.artifact_id, row.content, str(row.created_at))
        for row in artifact_rows.find(session_id=session_id)
        if row.artifact_id in artifact_ids
    ]


logger = logging.getLogger(__name__)


def build_artifacts_message_text(
    artifacts: list[tuple[str, dict, str]],
) -> str:
    parts = [ARTIFACT_MESSAGE_PREFIX]
    for artifact_id, content, created_at in artifacts:
        parts.append("")
        parts.append(render_artifact_text(artifact_id, content, created_at))
    return "\n".join(parts)


async def inject_artifacts_as_user_message(
    session: Session,
    artifact_ids: list[str],
    broadcast: BroadcastFn,
) -> bool:
    if not artifact_ids:
        return False

    artifacts = await asyncio.to_thread(load_artifacts, session.id, artifact_ids)
    if not artifacts:
        logger.warning(
            "No artifacts found for session %s with ids %s",
            session.id,
            artifact_ids,
        )
        return False

    text = build_artifacts_message_text(artifacts)
    message = MessageParam(
        role="user",
        content=[TextBlockParam(type="text", text=text)],
    )
    await persist_messages(session_id=session.id, messages=[message])

    await broadcast(
        BroadcastEvent(
            type="truncated",
            role="system",
            content=[],
            session_id=session.id,
        )
    )
    return True
