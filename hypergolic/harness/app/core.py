from __future__ import annotations

import copy
import logging
from typing import Callable

from hypergolic.config.models import DEFAULT_MODELS, SsoConfig, TierModel
from hypergolic.config.settings import (
    DEFAULT_STRIP_HISTORY_THINKING,
    DEFAULT_TRUNCATE_TOKEN_THRESHOLD,
    DEFAULT_TURN_COMPACTION_FLOOR_TOKENS,
)
from hypergolic.enums import ModelTier
from hypergolic.gates.model import Gate
from hypergolic.harness.app.lookup import find_skill
from hypergolic.harness.app.overrides import OverridesMixin
from hypergolic.harness.app.prompts import _UNSET, SystemPromptMixin
from hypergolic.harness.app.run import expand_paths, run_app
from hypergolic.harness.app.validation import validate_app
from hypergolic.harness.primitives.approval import MCPApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.bundles import Role, Skill, Workflow
from hypergolic.harness.primitives.tool import Tool, ToolRegistryMixin
from hypergolic.harness.project import Project
from hypergolic.contrib.roles.registry import ALL_CONTRIB_ROLES
from hypergolic.contrib.skills.registry import ALL_CONTRIB_SKILLS
from hypergolic.contrib.tools.registry import UNIVERSAL_TOOLS

MCPApprovalPolicy = Callable[[MCPApprovalContext], ToolApprovalDecision]

logger = logging.getLogger(__name__)


class App(SystemPromptMixin, OverridesMixin, ToolRegistryMixin):
    tools: list[Tool]

    def __init__(
        self,
        truncate_token_threshold: int = DEFAULT_TRUNCATE_TOKEN_THRESHOLD,
        strip_history_thinking: bool = DEFAULT_STRIP_HISTORY_THINKING,
        default_model_tier: ModelTier = ModelTier.MEDIUM,
        shape_grep_output: bool = True,
        knowledge_distillation: bool = True,
        harness_merge_gates: "list[Gate] | None" = None,
        max_dispatch_depth: int = 3,
        models: dict[ModelTier, TierModel] | None = None,
        turn_compaction_floor_tokens: int = DEFAULT_TURN_COMPACTION_FLOOR_TOKENS,
        sso: SsoConfig | None = None,
    ) -> None:
        self.truncate_token_threshold = truncate_token_threshold
        self.strip_history_thinking = strip_history_thinking
        self.default_model_tier = default_model_tier
        self.models = {**DEFAULT_MODELS, **(models or {})}
        self.turn_compaction_floor_tokens = turn_compaction_floor_tokens
        self.sso = sso or SsoConfig()
        # Regroup grep-style (path:lineno:text) command output by file.
        # See hypergolic.tools.grep_shaping.
        self.shape_grep_output = shape_grep_output
        self.knowledge_distillation = knowledge_distillation
        # Gate pipeline for landing /harness edits; app-level only, so no
        # project can become the ungated path for editing the rules.
        self.harness_merge_gates = harness_merge_gates
        # Longest dispatch chain, counting the top-level session: 3 lets a
        # child dispatch a grandchild, and the grandchild dispatches nothing.
        self.max_dispatch_depth = max_dispatch_depth
        self.projects: list[Project] = []
        self.tools = []
        self.roles: list[Role] = []
        self.skills: list[Skill] = []
        self.workflows: list[Workflow] = []
        self._mcp_servers: dict[str, dict] = {}
        self.mcp_approval_policy: MCPApprovalPolicy | None = None
        self._system_prompt = _UNSET
        self._appended_prompts = []

    def register_project(self, project: Project) -> None:
        self.projects.append(project)

    def register_projects(self, projects: list[Project]) -> None:
        self.projects.extend(projects)

    def register_role(self, role: Role) -> None:
        self.roles.append(_own(role))

    def register_roles(self, roles: list[Role]) -> None:
        self.roles.extend(map(_own, roles))

    def register_skill(self, skill: Skill) -> None:
        self.skills.append(skill)

    def register_skills(self, skills: list[Skill]) -> None:
        self.skills.extend(skills)

    def register_workflow(self, workflow: Workflow) -> None:
        self.workflows.append(workflow)

    def register_workflows(self, workflows: list[Workflow]) -> None:
        self.workflows.extend(workflows)

    def register_mcp_server(self, id: str, **kwargs: object) -> None:
        self._mcp_servers[id] = kwargs

    def use_defaults(self) -> None:
        """Register the built-in (contrib) tools, roles, and skills as deep
        copies, so ``override_*`` / ``modify_role`` can edit this App's graph
        without mutating the shared module-level contrib objects."""

        self.register_tools([copy.deepcopy(t) for t in UNIVERSAL_TOOLS])
        self.register_roles([copy.deepcopy(r) for r in ALL_CONTRIB_ROLES])
        self.register_skills([copy.deepcopy(s) for s in ALL_CONTRIB_SKILLS])

    def find_project(self, project_id: str) -> Project | None:
        """Project by id, or ``None``. Use wherever a missing project should be
        handled gracefully (e.g. a session whose project was removed/renamed in
        ``main.py``); use :meth:`get_project` only where absence is a bug."""
        return next((p for p in self.projects if p.id == project_id), None)

    def get_project(self, project_id: str) -> Project:
        project = self.find_project(project_id)
        if project is None:
            raise KeyError(f"Project '{project_id}' is not registered")
        return project

    def get_skill(self, skill_id: str) -> Skill | None:
        return find_skill(skill_id, self)

    def _validate(self) -> list[str]:
        return validate_app(self)

    def _expand_paths(self) -> None:
        expand_paths(self)

    def __call__(self) -> None:
        run_app(self)


def _own(role: Role) -> Role:
    lists = ("skills", "tools", "workflows", "dispatch_targets")
    return role.model_copy(update={f: list(getattr(role, f)) for f in lists})
