from enum import Enum


class ModelTier(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    EXTRA_HIGH = "Extra High"


class SessionStatus(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    STREAMING = "streaming"
    RETRYING = "retrying"
    TOOL_USE = "tool_use"
    TRUNCATING = "truncating"
    AWAITING_APPROVAL = "awaiting_approval"
    ERROR = "error"
    CONCLUDING = "concluding"
    CONCLUDED = "concluded"
    INTERRUPTED = "interrupted"


class WorkflowOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SUPPRESSED = "suppressed"
