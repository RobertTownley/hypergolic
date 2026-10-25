from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

class EgressMode(str, Enum):
    DENY_ALL = "deny_all"
    ALLOW_ALL = "allow_all"
    ALLOW = "allow"


class Egress(BaseModel):
    """Project-level outbound network policy.

    This is the agentic-escape boundary, not a network-isolation knob:
    containers always reach each other internally regardless of egress.
    """

    mode: EgressMode = EgressMode.DENY_ALL
    hosts: list[str] = Field(default_factory=list)

    @classmethod
    def DenyAll(cls) -> "Egress":
        return cls(mode=EgressMode.DENY_ALL)

    @classmethod
    def AllowAll(cls) -> "Egress":
        return cls(mode=EgressMode.ALLOW_ALL)

    @classmethod
    def Allow(cls, hosts: list[str]) -> "Egress":
        return cls(mode=EgressMode.ALLOW, hosts=list(hosts))

    @model_validator(mode="after")
    def _validate(self) -> "Egress":
        if self.mode is EgressMode.ALLOW and not self.hosts:
            raise ValueError("Egress.Allow requires at least one host")
        if self.mode is not EgressMode.ALLOW and self.hosts:
            raise ValueError(
                f"Egress hosts are only meaningful with Egress.Allow (got mode={self.mode.value})"
            )
        return self

    @property
    def is_restricted(self) -> bool:
        """True when a proxy must be compiled in (anything but AllowAll)."""
        return self.mode is not EgressMode.ALLOW_ALL

    @staticmethod
    def domain(host: str) -> str:
        """Reduce an allowlist entry (possibly a URL or host:port) to a domain."""
        h = host.split("://", 1)[-1]
        h = h.split("/", 1)[0]
        h = h.rsplit(":", 1)[0] if h.count(":") == 1 and h.rsplit(":", 1)[1].isdigit() else h
        return h
