import asyncio
import logging
from pathlib import Path

from hypergolic.config.settings import settings
from hypergolic.prompts.blocks import PromptBlock
from hypergolic.prompts.store import load_prompt_blocks, save_prompt_blocks
from hypergolic.harness.app.state import get_app
from hypergolic.harness.primitives.bundles import resolve_prompt
from hypergolic.schemas import Session
from hypergolic.skills import activation_rows
from hypergolic.workflows.resolver import get_session_workflow, get_workflow
from hypergolic.sandbox.model.egress import EgressMode
from hypergolic.sandbox.shared import KNOWLEDGE_DIR_NAME, PROPOSALS_DIR_NAME, shared_dir

logger = logging.getLogger(__name__)

_GENERALIST_MD = Path(__file__).resolve().parent.parent / "contrib" / "prompts" / "roles" / "generalist.md"
DEFAULT_SYSTEM_PROMPT = _GENERALIST_MD.read_text()


def _egress_summary(egress) -> str:
    if egress.mode is EgressMode.ALLOW_ALL:
        return "allow all"
    if egress.mode is EgressMode.ALLOW:
        domains = [egress.domain(h) for h in egress.hosts]
        return "limited to " + ", ".join(domains)
    return "deny all"


def _sandbox_context_lines(session: Session) -> list[str]:
    if settings.HYPERGOLIC_DANGEROUSLY_AUTO_APPROVE:
        return [
            "DANGEROUSLY_AUTO_APPROVE: no sandbox — cmd runs directly "
            "on the host; approval gates auto-approve"
        ]

    app = get_app()
    project = app.find_project(session.project_id)
    sandbox = project.resolved_sandbox if project else None
    if sandbox is None:
        return []

    multi = len(sandbox.containers) > 1
    noun = "containers" if multi else "container"
    lines = [
        f"Sandbox {sandbox.id}: {noun} {', '.join(sandbox.container_ids)}; "
        f"egress {_egress_summary(sandbox.egress)}"
    ]
    mounts = []
    for c in sandbox.containers:
        for m in c.host_mounts:
            scope = f" ({c.id})" if multi else ""
            mode = "ro" if m.read_only else "rw"
            mounts.append(f"host {m.source} {mode} {m.target}{scope}")
    if mounts:
        lines.append("Extra mounts: " + "; ".join(mounts))
    if multi:
        lines.append("Worktree at /app is one shared tree across containers")
    return lines


def _session_context_block(session: Session) -> PromptBlock | None:
    lines = _sandbox_context_lines(session)
    if not lines:
        return None
    return PromptBlock(source="Session context", text="# Session Context\n" + "\n".join(lines) + "\n")


def _build_workflow_prompt_blocks(session: Session) -> list[PromptBlock]:
    blocks: list[PromptBlock] = []
    app = get_app()

    wf_state = get_session_workflow(session.id)
    if wf_state is None:
        return blocks

    workflow_id, current_state_id = wf_state
    wf = get_workflow(workflow_id)
    if wf is None:
        return blocks

    wf_content = resolve_prompt(wf, app)
    if wf_content:
        blocks.append(PromptBlock(
            source=f"Workflow: {wf.name}",
            text=wf_content,
        ))

    state = None
    for s in wf.states:
        if s.id == current_state_id:
            state = s
            break

    if state is None:
        return blocks

    state_content = resolve_prompt(state, app)
    if state_content:
        blocks.append(PromptBlock(
            source=f"Workflow State: {state.name}",
            text=state_content,
        ))

    return blocks


_KNOWLEDGE_INDEX_MAX_CHARS = 6_000


def _knowledge_index_block(project_id: str) -> PromptBlock | None:
    readme = shared_dir(project_id) / KNOWLEDGE_DIR_NAME / "README.md"
    try:
        text = readme.read_text()
    except OSError:
        return None
    if not text.strip():
        return None
    if len(text) > _KNOWLEDGE_INDEX_MAX_CHARS:
        text = text[:_KNOWLEDGE_INDEX_MAX_CHARS] + "\n[truncated — index exceeds budget; trim it]"
    return PromptBlock(
        source="Knowledge base index",
        text=f"/shared/knowledge/README.md (accumulated project+user knowledge):\n\n{text}",
    )


def _proposals_block(project_id: str) -> PromptBlock | None:
    names = sorted(
        f.name for f in (shared_dir(project_id) / PROPOSALS_DIR_NAME).glob("*.md")
    )
    if not names:
        return None
    return PromptBlock(
        source="Harness proposals",
        text=(
            f"Open harness-improvement proposals in /shared/{PROPOSALS_DIR_NAME}: "
            f"{', '.join(names)}. When one overlaps your work (or the user asks), "
            "read it and implement, revise, or delete it "
            "(`activate_skill harness-engineering`)."
        ),
    )


def _build_frozen_blocks(session: Session) -> list[PromptBlock]:
    blocks: list[PromptBlock] = []
    app = get_app()

    base_role = app.get_role("generalist")
    base_content = resolve_prompt(base_role, app) if base_role else None
    base_prompt = app.resolve_system_prompt(base_content or DEFAULT_SYSTEM_PROMPT)
    if base_prompt is not None:
        blocks.append(PromptBlock(source="Base prompt", text=base_prompt))

    for text in app.resolve_appended_prompts():
        if text.strip():
            blocks.append(PromptBlock(source="User guidance", text=text))

    if session.role != "generalist":
        role = app.get_role(session.role)
        if role:
            role_content = resolve_prompt(role, app)
            if role_content:
                blocks.append(PromptBlock(
                    source=f"Role prompt ({session.role})",
                    text=role_content,
                ))

    project = app.find_project(session.project_id)
    if project:
        project_prompt = resolve_prompt(project, app)
        if project_prompt:
            blocks.append(PromptBlock(
                source="User-project guidance",
                text=project_prompt,
            ))

        kb = _knowledge_index_block(project.id)
        if kb:
            blocks.append(kb)
        proposals = _proposals_block(project.id)
        if proposals:
            blocks.append(proposals)

    context = _session_context_block(session)
    if context:
        blocks.append(context)

    if session.dispatch_prompt:
        blocks.append(PromptBlock(source="Dispatch context", text=session.dispatch_prompt))

    return blocks


async def frozen_prompt_blocks(session: Session, *, persist: bool) -> list[PromptBlock]:
    stored = await asyncio.to_thread(load_prompt_blocks, session.id)
    if stored is not None:
        return stored
    blocks = await asyncio.to_thread(_build_frozen_blocks, session)
    if persist:
        await asyncio.to_thread(save_prompt_blocks, session.id, blocks)
    return blocks


def _build_activated_skills_block(session: Session) -> PromptBlock | None:
    skills = activation_rows.skill_ids(session.id)
    if not skills:
        return None
    return PromptBlock(
        source="Activated skills",
        text=(
            "# Activated Skills\n"
            f"Activated earlier this session: {', '.join(skills)}. Their guidance "
            "is not in your context if the turn that loaded it has been compacted; "
            "`activate_skill <id>` reloads it when the work calls for it.\n"
        ),
    )


def _build_live_blocks(session: Session) -> list[PromptBlock]:
    blocks = _build_workflow_prompt_blocks(session)
    skills = _build_activated_skills_block(session)
    if skills:
        blocks.append(skills)
    return blocks


async def live_prompt_blocks(session: Session) -> list[PromptBlock]:
    return await asyncio.to_thread(_build_live_blocks, session)


async def build_prompt_blocks(session: Session) -> list[PromptBlock]:
    frozen = await frozen_prompt_blocks(session, persist=False)
    return frozen + await live_prompt_blocks(session)
