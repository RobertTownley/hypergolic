import json
from typing import Any


def render_artifact_text(artifact_id: str, content: dict[str, Any], created_at: str) -> str:
    parts = [f"# Artifact: {artifact_id} ({created_at})"]
    for key, value in content.items():
        if isinstance(value, str):
            parts.append(f"\n{value}")
        elif isinstance(value, list):
            parts.append(f"\n**{key.replace('_', ' ').title()}:** {json.dumps(value)}")
        else:
            parts.append(f"\n**{key.replace('_', ' ').title()}:** {json.dumps(value)}")
    return "\n".join(parts)
