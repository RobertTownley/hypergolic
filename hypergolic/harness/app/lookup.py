from __future__ import annotations

from typing import Protocol

from hypergolic.harness.primitives.bundles import Role, Skill, Workflow
from hypergolic.harness.project import Project


class _SkillSearchable(Protocol):
    skills: list[Skill]
    projects: list[Project]
    roles: list[Role]
    workflows: list[Workflow]


def all_workflows(app: _SkillSearchable) -> list[Workflow]:
    return [
        *app.workflows,
        *(wf for p in app.projects for wf in p.workflows),
        *(wf for r in app.roles for wf in r.workflows),
    ]


def scoped_workflows(
    app: _SkillSearchable, project: Project | None, role: Role | None,
) -> list[Workflow]:
    return [
        *app.workflows,
        *(project.workflows if project else []),
        *(role.workflows if role else []),
    ]


def unique_workflows(workflows: list[Workflow]) -> list[Workflow]:
    by_id: dict[str, Workflow] = {}
    for wf in workflows:
        by_id.setdefault(wf.id, wf)
    return list(by_id.values())


def find_workflow(workflows: list[Workflow], workflow_id: str) -> Workflow | None:
    return next((wf for wf in workflows if wf.id == workflow_id), None)


def find_scoped_workflow(
    app: _SkillSearchable, project: Project | None, role: Role | None,
    workflow_id: str,
) -> Workflow | None:
    return find_workflow(scoped_workflows(app, project, role), workflow_id)


def collect_top_level_skills(app: _SkillSearchable) -> list[Skill]:
    """Collect all top-level Skill objects from every registration point.

    Walks: app skills, project skills, role skills, workflow skills,
    workflow state skills, project workflow skills, project workflow state skills.

    Returns top-level skills only (not recursively flattened children).
    """
    result: list[Skill] = []
    result.extend(app.skills)
    for p in app.projects:
        result.extend(p.skills)
    for r in app.roles:
        result.extend(r.skills)
    for wf in all_workflows(app):
        result.extend(wf.skills)
        for state in wf.states:
            result.extend(state.skills)
    return result


def _find_in_skill(skill_id: str, skill: Skill) -> Skill | None:
    """Recursively search a skill and its children for a matching ID."""
    if skill.id == skill_id:
        return skill
    for child in skill.skills:
        found = _find_in_skill(skill_id, child)
        if found:
            return found
    return None


def find_skill(skill_id: str, app: _SkillSearchable) -> Skill | None:
    for s in collect_top_level_skills(app):
        found = _find_in_skill(skill_id, s)
        if found:
            return found
    return None
