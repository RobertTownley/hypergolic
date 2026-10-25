import asyncio

from fastapi import APIRouter

from hypergolic.mcptools.sessions import get_enabled_servers
from hypergolic.prompts.builder import build_prompt_blocks
from hypergolic.schemas import Session
from hypergolic.sessions.operations import load_session
from hypergolic.sessions.schemas import (
    PromptPartInfo,
    SessionContextResponse,
    SkillInfo,
    SkillsSummary,
    ToolInfo,
)
from hypergolic.sessions.transformers import build_skill_infos, command_tool_infos
from hypergolic.skills import activation_rows
from hypergolic.skills.resolver import resolve_session_skills
from hypergolic.workflows.resolver import resolve_workflows_for_session
from hypergolic.workflows.schemas import (
    WorkflowDetailResponse,
    WorkflowOutputSchemaDetail,
    WorkflowSkillDetail,
    WorkflowStateDetail,
    WorkflowToolDetail,
)

router = APIRouter()


async def _build_session_context(session: Session) -> SessionContextResponse:
    tool_infos: list[ToolInfo] = await asyncio.to_thread(command_tool_infos, session)
    all_skills = await asyncio.to_thread(resolve_session_skills, session)
    mcp_enabled = list(await asyncio.to_thread(get_enabled_servers, session.id))
    activated = await asyncio.to_thread(activation_rows.skill_ids, session.id)
    blocks = await build_prompt_blocks(session)
    return SessionContextResponse(
        tools=tool_infos,
        tools_count=len(tool_infos),
        tools_token_estimate=sum(info.token_estimate for info in tool_infos),
        skills_summary=SkillsSummary(total=len(all_skills), activated=activated),
        mcp_enabled=mcp_enabled,
        prompt_token_estimate=sum(len(b.text) // 4 for b in blocks),
    )


@router.get("/{session_id}/context", response_model=SessionContextResponse)
async def get_session_context(session_id: str):
    session = await asyncio.to_thread(load_session, session_id)
    return await _build_session_context(session)


@router.get("/{session_id}/prompt", response_model=list[PromptPartInfo])
async def get_session_prompt(session_id: str):
    session = await asyncio.to_thread(load_session, session_id)
    blocks = await build_prompt_blocks(session)
    return [
        PromptPartInfo(source=b.source, content=b.text, token_estimate=len(b.text) // 4)
        for b in blocks
    ]


@router.get("/{session_id}/workflows", response_model=list[WorkflowDetailResponse])
def get_session_workflows(session_id: str):
    session = load_session(session_id)
    return [_workflow_detail(wf) for wf in resolve_workflows_for_session(session)]


def _workflow_detail(wf) -> WorkflowDetailResponse:
    return WorkflowDetailResponse(
        id=wf.id,
        name=wf.name,
        description=wf.description or "",
        prompt_path=wf.prompt_path,
        initial_state=wf.initial_state,
        states=[
            WorkflowStateDetail(
                id=s.id,
                name=s.name,
                prompt_path=s.prompt_path,
                skills=[WorkflowSkillDetail(id=sk.id, name=sk.name) for sk in s.skills],
                tools=[
                    WorkflowToolDetail(id=t.id, name=t.name, description=t.description)
                    for t in s.tools
                ],
                truncate_on_entry=s.truncate_on_entry,
                include_artifacts=s.include_artifacts,
                output_schemas=[
                    WorkflowOutputSchemaDetail(
                        outcome=o.outcome,
                        next_state=o.next_state,
                        artifact_id=o.artifact_id,
                        requires_approval=o.requires_approval,
                        has_approval_view=o.approval_view is not None,
                        schema_def=o.schema_def,
                    )
                    for o in s.output_schemas
                ],
            )
            for s in wf.states
        ],
    )


@router.get("/{session_id}/skills", response_model=list[SkillInfo])
def get_session_skills(session_id: str):
    session = load_session(session_id)
    return build_skill_infos(resolve_session_skills(session))
