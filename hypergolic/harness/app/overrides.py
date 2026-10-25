"""Editing the default tool/skill/role/workflow graph without forking it."""

from __future__ import annotations

import logging

from hypergolic.harness.app.prompts import _SystemPrompt
from hypergolic.harness.primitives.bundles import Role, Skill, Workflow, resolve_prompt
from hypergolic.harness.primitives.tool import Tool

logger = logging.getLogger(__name__)


class OverridesMixin:
    tools: list[Tool]
    roles: list[Role]
    skills: list[Skill]
    workflows: list[Workflow]

    def get_role(self, role_id: str) -> Role | None:
        return next((r for r in self.roles if r.id == role_id), None)

    def _require_role(self, role_id: str) -> Role:
        role = self.get_role(role_id)
        if role is None:
            raise KeyError(f"Role '{role_id}' is not registered")
        return role

    @staticmethod
    def _normalize_prompt_fields(fields: dict) -> dict:
        """Setting one prompt source clears the other two (exclusivity)."""
        prompt_keys = ("prompt", "prompt_path", "prompt_fn")
        if any(k in fields for k in prompt_keys):
            fields = dict(fields)
            for k in prompt_keys:
                fields.setdefault(k, None)
        return fields

    def _containers(self) -> list:
        """Every Skill/Role/Workflow/WorkflowState reachable from the registries."""
        seen: set[int] = set()
        out: list = []

        def add_skill(s: Skill) -> None:
            if id(s) in seen:
                return
            seen.add(id(s))
            out.append(s)
            for child in s.skills:
                add_skill(child)

        def add_workflow(wf: Workflow) -> None:
            if id(wf) in seen:
                return
            seen.add(id(wf))
            out.append(wf)
            for s in wf.skills:
                add_skill(s)
            for st in wf.states:
                if id(st) not in seen:
                    seen.add(id(st))
                    out.append(st)
                    for s in st.skills:
                        add_skill(s)

        for s in self.skills:
            add_skill(s)
        for r in self.roles:
            out.append(r)
            for s in r.skills:
                add_skill(s)
            for wf in r.workflows:
                add_workflow(wf)
        for wf in self.workflows:
            add_workflow(wf)
        return out

    def _tool_lists(self) -> list[list]:
        return [self.tools, *(c.tools for c in self._containers())]

    def _skill_lists(self) -> list[list]:
        return [self.skills, *(c.skills for c in self._containers() if hasattr(c, "skills"))]

    @staticmethod
    def _replace_everywhere(lists: list[list], item_id: str, fields: dict, kind: str) -> None:
        replacement = None
        found = False
        for lst in lists:
            for i, item in enumerate(lst):
                if item.id == item_id:
                    if replacement is None:
                        replacement = item.model_copy(update=fields)
                    lst[i] = replacement
                    found = True
        if not found:
            raise KeyError(f"{kind} '{item_id}' is not registered")

    @staticmethod
    def _drop_everywhere(lists: list[list], item_id: str, kind: str) -> None:
        found = False
        for lst in lists:
            kept = [x for x in lst if x.id != item_id]
            if len(kept) != len(lst):
                lst[:] = kept
                found = True
        if not found:
            raise KeyError(f"{kind} '{item_id}' is not registered")

    def override_tool(self, tool_id: str, **fields: object) -> None:
        """Replace fields on a registered tool, everywhere it appears."""
        self._replace_everywhere(self._tool_lists(), tool_id, self._normalize_prompt_fields(fields), "Tool")

    def remove_tool(self, tool_id: str) -> None:
        """Drop a tool everywhere it appears (app, roles, skills, workflows)."""
        self._drop_everywhere(self._tool_lists(), tool_id, "Tool")

    def override_skill(self, skill_id: str, **fields: object) -> None:
        """Replace fields on a registered skill, everywhere it appears."""
        self._replace_everywhere(self._skill_lists(), skill_id, self._normalize_prompt_fields(fields), "Skill")

    def remove_skill(self, skill_id: str, *, role_id: str | None = None) -> None:
        """Drop a skill from a single role (``role_id=...``) or everywhere."""
        if role_id is not None:
            role = self._require_role(role_id)
            if skill_id not in {s.id for s in role.skills}:
                raise KeyError(f"Skill '{skill_id}' is not on role '{role_id}'")
            self.modify_role(role_id, remove_skills=[skill_id])
            return
        self._drop_everywhere(self._skill_lists(), skill_id, "Skill")

    def override_role(self, role_id: str, **fields: object) -> None:
        """Replace fields on a registered role (e.g. its prompt)."""
        fields = self._normalize_prompt_fields(fields)
        for i, r in enumerate(self.roles):
            if r.id == role_id:
                self.roles[i] = r.model_copy(update=fields)
                return
        raise KeyError(f"Role '{role_id}' is not registered")

    def append_role_prompt(self, role_id: str, path: str | None = None, prompt: str | None = None) -> None:
        """Append guidance after a registered role's prompt, keeping it intact.

        May be called multiple times; additions stack in order. Pass exactly
        one of ``path`` (``~`` expanded; read lazily per session) or ``prompt``.
        """
        self._require_role(role_id)
        addition = _SystemPrompt.one_of(path, prompt)
        original = self._require_role(role_id).model_copy()

        def combined(app, _orig=original, _add=addition) -> str:
            base = resolve_prompt(_orig, app)
            extra = _add.read()
            return f"{base.rstrip()}\n\n{extra}" if base else extra

        self.override_role(role_id, prompt_fn=combined)

    def modify_role(
        self,
        role_id: str,
        *,
        add_tools: list[Tool] | None = None,
        remove_tools: list[str] | None = None,
        add_skills: list[Skill] | None = None,
        remove_skills: list[str] | None = None,
        add_workflows: list[Workflow] | None = None,
        remove_workflows: list[str] | None = None,
        add_dispatch_targets: list[str] | None = None,
        remove_dispatch_targets: list[str] | None = None,
    ) -> None:
        """Add/remove tools, skills, workflows, or dispatch targets on a role."""
        role = self._require_role(role_id)
        self._edit_by_id(role.tools, add_tools, remove_tools, role_id, "tool")
        self._edit_by_id(role.skills, add_skills, remove_skills, role_id, "skill")
        self._edit_by_id(role.workflows, add_workflows, remove_workflows, role_id, "workflow")
        for target in add_dispatch_targets or []:
            if target not in role.dispatch_targets:
                role.dispatch_targets.append(target)
        if remove_dispatch_targets:
            role.dispatch_targets[:] = [
                t for t in role.dispatch_targets if t not in remove_dispatch_targets
            ]

    @staticmethod
    def _edit_by_id(target: list, additions: list | None, removal_ids: list[str] | None,
                    role_id: str, kind: str) -> None:
        if removal_ids:
            present = {x.id for x in target}
            for rid in removal_ids:
                if rid not in present:
                    logger.warning("modify_role(%r): no %s %r to remove", role_id, kind, rid)
            drop = set(removal_ids)
            target[:] = [x for x in target if x.id not in drop]
        if additions:
            existing = {x.id for x in target}
            for x in additions:
                if x.id not in existing:
                    target.append(x)
                    existing.add(x.id)
