from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, model_validator


class ValidationOutcome(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class ValidationResult(BaseModel):
    outcome: ValidationOutcome
    message: str | None = None

    @classmethod
    def valid(cls, message: str | None = None) -> "ValidationResult":
        return cls(outcome=ValidationOutcome.VALID, message=message)

    @classmethod
    def invalid(cls, message: str) -> "ValidationResult":
        return cls(outcome=ValidationOutcome.INVALID, message=message)

    @property
    def is_valid(self) -> bool:
        return self.outcome == ValidationOutcome.VALID

    @model_validator(mode="after")
    def _invalid_needs_message(self) -> "ValidationResult":
        if not self.is_valid and not self.message:
            raise ValueError("An INVALID ValidationResult needs a message.")
        return self
