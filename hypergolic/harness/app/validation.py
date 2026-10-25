from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from hypergolic.harness.app.lookup import (
    all_workflows,
    collect_top_level_skills,
    unique_workflows,
)
from hypergolic.harness.primitives.bundles import Skill

if TYPE_CHECKING:
    from hypergolic.harness.app.core import App


def _collect_all_skills(skills: list[Skill]) -> list[Skill]:
    """Recursively collect all skills including nested children."""
    result: list[Skill] = []
    for skill in skills:
        result.append(skill)
        result.extend(_collect_all_skills(skill.skills))
    return result


def _detect_skill_cycles(all_skills: list[Skill]) -> list[str]:
    """Detect circular dependencies in skill nesting. Returns cycle path strings."""
    # Build adjacency list
    graph: dict[str, list[str]] = {}
    for skill in all_skills:
        if skill.id not in graph:
            graph[skill.id] = []
        for child in skill.skills:
            graph[skill.id].append(child.id)

    errors: list[str] = []
    visited: set[str] = set()
    in_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        if node in in_stack:
            # Found a cycle — extract the cycle portion of the path
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            errors.append(f"Circular skill dependency detected: {' -> '.join(cycle)}")
            return
        if node in visited:
            return

        visited.add(node)
        in_stack.add(node)
        path.append(node)

        for neighbor in graph.get(node, []):
            dfs(neighbor)

        path.pop()
        in_stack.remove(node)

    for node in graph:
        if node not in visited:
            dfs(node)

    return errors


def _duplicate_ids(sources: list[list], label: str) -> list[str]:
    errors: list[str] = []
    for source in sources:
        seen_in_source: set[str] = set()
        for item in source:
            if item.id in seen_in_source:
                errors.append(f"Duplicate {label} ID: '{item.id}'")
            seen_in_source.add(item.id)
    return errors


def _validate_roles(app: App) -> list[str]:
    errors: list[str] = []
    if not app.roles:
        errors.append(
            "No roles registered. Register at least the base roles with app.register_roles(ALL_CONTRIB_ROLES)."
        )
    role_ids = [r.id for r in app.roles]
    if app.roles and "generalist" not in role_ids:
        errors.append(
            "No 'generalist' role registered. The generalist role is required as the default session role."
        )
    role_id_set = set(role_ids)
    for r in app.roles:
        for target in r.dispatch_targets:
            if target not in role_id_set:
                errors.append(
                    f"Role '{r.id}' dispatch target '{target}' is not a registered role"
                )
    return errors


def _validate_tools(app: App) -> list[str]:
    # The same ID may legitimately appear across sources -- e.g. every project
    # that configures a sandbox registers a tool with id "cmd" -- so only
    # same-source collisions are flagged.
    return _duplicate_ids([
        list(app.tools),
        *[list(p.tools) for p in app.projects],
        *[list(wf.tools) for wf in all_workflows(app)],
    ], "tool")


def _validate_projects(app: App) -> list[str]:
    errors = _duplicate_ids([list(app.projects)], "project")
    for p in app.projects:
        root = Path(p.git_root).expanduser()
        if not root.exists():
            errors.append(f"Project '{p.id}' git_root does not exist: {root}")
        elif not (root / ".git").exists():
            errors.append(f"Project '{p.id}' git_root is not a git repo: {root}")
    for p in app.projects:
        if p.prompt_path:
            path = Path(p.prompt_path).expanduser()
            if not path.exists():
                errors.append(f"Project '{p.id}' prompt_path not found: {path}")
    return errors


def _validate_workflows(app: App) -> list[str]:
    errors: list[str] = []
    for wf in unique_workflows(all_workflows(app)):
        state_ids = {s.id for s in wf.states}
        if wf.initial_state not in state_ids:
            errors.append(
                f"Workflow '{wf.id}' initial_state '{wf.initial_state}' not found in states"
            )
        for s in wf.states:
            for o in s.output_schemas:
                if o.next_state and o.next_state not in state_ids:
                    errors.append(
                        f"Workflow '{wf.id}' state '{s.id}' output references unknown state '{o.next_state}'"
                    )
    return errors


def _skill_sources(app: App) -> list[list[Skill]]:
    sources: list[list[Skill]] = [
        list(app.skills),
        *[list(r.skills) for r in app.roles],
        *[list(p.skills) for p in app.projects],
    ]
    for wf in all_workflows(app):
        sources.append(list(wf.skills))
        for state in wf.states:
            sources.append(list(state.skills))
    return sources


def _validate_skills(app: App) -> list[str]:
    # Cross-source duplicates (and re-declared built-ins) are the same skill;
    # only same-source collisions are flagged.
    errors = _duplicate_ids(
        [_collect_all_skills(source) for source in _skill_sources(app)], "skill",
    )
    unique_skills: list[Skill] = []
    seen_skill_ids: set[str] = set()
    for skill in _collect_all_skills(collect_top_level_skills(app)):
        if skill.id not in seen_skill_ids:
            seen_skill_ids.add(skill.id)
            unique_skills.append(skill)
    errors.extend(_detect_skill_cycles(unique_skills))
    return errors


def validate_app(app: App) -> list[str]:
    """Return a list of configuration error strings (empty = valid)."""
    return [
        *_validate_roles(app),
        *_validate_tools(app),
        *_validate_projects(app),
        *_validate_workflows(app),
        *_validate_skills(app),
    ]
