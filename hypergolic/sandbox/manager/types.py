"""Shared sandbox types and errors."""

from dataclasses import dataclass


class SandboxUnavailableError(Exception):
    """Raised when Docker is not available."""


class SandboxError(Exception):
    """Raised when a sandbox operation fails."""


class SandboxTimeout(SandboxError):
    """An exec hit its deadline. Carries whatever the command printed before
    the kill so a timeout is a partial answer, not a blackout."""

    def __init__(self, message: str, stdout: str = "", stderr: str = ""):
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


class SandboxNotReadyError(SandboxError):
    """Raised when the sandbox hasn't finished starting.

    Distinct from a failure: a caller that isn't the one driving startup (the
    file browser, a readiness probe) should say "starting" and retry rather
    than surface an error.
    """


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    returncode: int
