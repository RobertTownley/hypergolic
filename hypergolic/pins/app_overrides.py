from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App


class AppOverrides(BaseModel):
    strip_history_thinking: bool | None = Field(
        default=None, description="Override App.strip_history_thinking for the session and every role",
    )
    truncate_token_threshold: int | None = Field(
        default=None, ge=1, description="Override App.truncate_token_threshold",
    )
    turn_compaction_floor_tokens: int | None = Field(
        default=None, ge=0, description="Override App.turn_compaction_floor_tokens; 0 disables",
    )
    shape_grep_output: bool | None = Field(default=None, description="Override App.shape_grep_output")

    def set_values(self) -> dict[str, object]:
        return self.model_dump(include=set(OVERRIDE_FIELDS), exclude_none=True)


OVERRIDE_FIELDS = tuple(AppOverrides.model_fields)


def overridden_app(base: "App", overrides: dict[str, object]) -> "App":
    app = copy.copy(base)
    for name, value in overrides.items():
        setattr(app, name, value)
    if "strip_history_thinking" in overrides:
        app.roles = [
            r.model_copy(update={"strip_history_thinking": overrides["strip_history_thinking"]})
            for r in base.roles
        ]
    return app
