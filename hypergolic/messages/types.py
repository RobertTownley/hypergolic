from dataclasses import dataclass
from typing import Any, Awaitable, Callable


# Up to MAX_STREAM_RETRIES + 1 total attempts. Delays between attempts are
# exponential with jitter, capped at RETRY_MAX_DELAY:
# min(RETRY_BASE_DELAY * 2**attempt, RETRY_MAX_DELAY) * uniform(0.5, 1.5)
# → ~1s, 2s, 4s, 8s, 10s, 10s, 10s, 10s (about a 1 minute budget).
MAX_STREAM_RETRIES = 8
RETRY_BASE_DELAY = 1.0
RETRY_MAX_DELAY = 10.0

# UI-only keys carried on stored content blocks. ``load_session_messages``
# strips them, so the provider never sees them and the transcript can hold
# structured facts the model doesn't need to re-read as prose.
EXCLUDED_CONTENT_FIELDS = {"parsed_output", "caller", "meta"}
EXCLUDED_FIELDS = {"parsed_output", "caller", "meta"}

INTERRUPTED_SUFFIX = "\n\n---\n*[Response interrupted by user]*"

# Prefixes that identify system-synthesized user-role messages (they carry the
# "user" role for the API but aren't user-authored). Genuine user input is
# preserved across summarization truncation; these synthesized messages are
# not, so they can't accumulate across repeated truncations.
CONVERSATION_SUMMARY_PREFIX = "[Conversation Summary]"
TURN_SUMMARY_PREFIX = "[Turn Summary]"
UNSUMMARIZED_CONTENT_PREFIX = "[Unsummarized Content]"
ARTIFACT_MESSAGE_PREFIX = (
    "The following artifacts from prior workflow states are the source of "
    "truth for this state."
)


class ModelRefusal(Exception):
    pass


class UserInterrupt(Exception):
    def __init__(self, partial_text: str | None = None):
        super().__init__()
        self.partial_text = partial_text


# TODO: type `content` more strictly — currently Any because each event type
# (content_block_start, tool_result, session_status_change, workflow_state_change, etc.)
# puts different shapes in here. A union of typed event dataclasses would be ideal.
@dataclass
class BroadcastEvent:
    type: str
    role: str
    content: Any
    session_id: str | None = None
    model: str | None = None
    stop_reason: str | None = None
    message_id: str | None = None
    usage: dict | None = None


BroadcastFn = Callable[[BroadcastEvent], Awaitable[None]]
