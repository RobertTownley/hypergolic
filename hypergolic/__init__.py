# Trust-store injection must precede every other hypergolic import: urllib3 and
# botocore capture ssl.SSLContext at import time, so any module that reaches them
# before this runs would verify TLS against certifi instead of the OS store.
from hypergolic.ssl_bootstrap import ensure_truststore

ensure_truststore()

# The public API loads on first attribute access (PEP 562), so importing a small
# submodule such as ``hypergolic.enums`` does not pull in the whole app.
import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from hypergolic.config.models import SsoConfig, TierModel
    from hypergolic.enums import ModelTier
    from hypergolic.harness.app.core import App, MCPApprovalPolicy
    from hypergolic.harness.primitives.approval import (
        ApprovalContext,
        MCPApprovalContext,
        ToolApprovalDecision,
    )
    from hypergolic.harness.primitives.bundles import (
        OutputSchema,
        Role,
        Skill,
        Workflow,
        WorkflowState,
    )
    from hypergolic.harness.primitives.results import InputSchema, ToolResult
    from hypergolic.harness.primitives.tool import Tool, ToolContext
    from hypergolic.harness.primitives.validation import ValidationOutcome, ValidationResult
    from hypergolic.harness.project import Project
    from hypergolic.tools.approval_view import (
        ApprovalView,
        BadgeBlock,
        CodeBlock,
        ForEachBlock,
        MarkdownBlock,
        TextBlock,
    )

_EXPORTS = {
    "App": "hypergolic.harness.app.core",
    "MCPApprovalPolicy": "hypergolic.harness.app.core",
    "ApprovalContext": "hypergolic.harness.primitives.approval",
    "MCPApprovalContext": "hypergolic.harness.primitives.approval",
    "ToolApprovalDecision": "hypergolic.harness.primitives.approval",
    "OutputSchema": "hypergolic.harness.primitives.bundles",
    "Role": "hypergolic.harness.primitives.bundles",
    "Skill": "hypergolic.harness.primitives.bundles",
    "Workflow": "hypergolic.harness.primitives.bundles",
    "WorkflowState": "hypergolic.harness.primitives.bundles",
    "InputSchema": "hypergolic.harness.primitives.results",
    "ToolResult": "hypergolic.harness.primitives.results",
    "ValidationOutcome": "hypergolic.harness.primitives.validation",
    "ValidationResult": "hypergolic.harness.primitives.validation",
    "Tool": "hypergolic.harness.primitives.tool",
    "ToolContext": "hypergolic.harness.primitives.tool",
    "ApprovalView": "hypergolic.tools.approval_view",
    "BadgeBlock": "hypergolic.tools.approval_view",
    "CodeBlock": "hypergolic.tools.approval_view",
    "ForEachBlock": "hypergolic.tools.approval_view",
    "MarkdownBlock": "hypergolic.tools.approval_view",
    "TextBlock": "hypergolic.tools.approval_view",
    "Project": "hypergolic.harness.project",
    "ModelTier": "hypergolic.enums",
    "TierModel": "hypergolic.config.models",
    "SsoConfig": "hypergolic.config.models",
}

__all__ = [
    "App",
    "ApprovalContext",
    "ApprovalView",
    "BadgeBlock",
    "CodeBlock",
    "ForEachBlock",
    "InputSchema",
    "MCPApprovalContext",
    "MCPApprovalPolicy",
    "MarkdownBlock",
    "ModelTier",
    "OutputSchema",
    "Project",
    "Role",
    "Skill",
    "SsoConfig",
    "TextBlock",
    "TierModel",
    "Tool",
    "ToolApprovalDecision",
    "ToolContext",
    "ToolResult",
    "ValidationOutcome",
    "ValidationResult",
    "Workflow",
    "WorkflowState",
]



def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'hypergolic' has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted([*globals(), *_EXPORTS])
