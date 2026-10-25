"""Built-in workflows shipped with Hypergolic.

These are registered by the default ``main.py`` so every user has
``Product Development``, ``Debugging``, and ``Optimize Config`` available
in the chat input's workflow selector without any harness configuration.

State prompts live alongside each workflow's package under
``hypergolic/contrib/prompts/workflows/`` and are read straight from the
installed package via ``contrib_path()``.
"""
from hypergolic.contrib.workflows.debug import debug_workflow
from hypergolic.contrib.workflows.feature_development import feature_development_workflow
from hypergolic.contrib.workflows.optimize_config import optimize_config_workflow

ALL_CONTRIB_WORKFLOWS = [
    feature_development_workflow,
    debug_workflow,
    optimize_config_workflow,
]

__all__ = [
    "ALL_CONTRIB_WORKFLOWS",
    "debug_workflow",
    "feature_development_workflow",
    "optimize_config_workflow",
]
