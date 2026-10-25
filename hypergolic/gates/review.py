from __future__ import annotations

import asyncio
import time

from hypergolic.gates.model import AgenticReview
from hypergolic.gates.request import GateVerdict, LandRequest, passed
from hypergolic.git.commands import git_checked
from hypergolic.git.merge_commit import (
    MergeInfo,
    clean_merge_summary,
    combined_patch,
    inspect_merge,
)

MAX_INLINE_REVIEW_DIFF = 24_000
MAX_LISTED_MERGE_COMMITS = 100


async def run_agentic_review(gate: AgenticReview, req: LandRequest) -> GateVerdict:
    from hypergolic.contrib.tools.dispatch import DISPATCH_PROMPT
    from hypergolic.dispatch.runner import dispatch

    started = time.monotonic()
    try:
        prompt = await _review_prompt(gate, req)
    except Exception as exc:
        return GateVerdict(ok=False, lines=[f"✗ {gate.label}: {exc}"])
    result = await dispatch(
        parent_session_id=req.session.id,
        content_blocks=[{"type": "text", "text": prompt}],
        dispatch_prompt=DISPATCH_PROMPT,
        broadcast=req.broadcast,
        role="reviewer",
        model_tier=gate.model_tier,
    )
    if result.outcome != "success":
        return GateVerdict(ok=False, lines=[
            f"✗ {gate.label}: reviewer {result.outcome}", result.conclusion,
        ])
    text = (result.reply_text if result.auto_concluded else result.conclusion) or ""
    verdict_line = _verdict_line(text)
    if "REQUEST_CHANGES" in verdict_line or "REQUEST CHANGES" in verdict_line:
        return GateVerdict(ok=False, lines=[
            f"✗ {gate.label}: requesting changes", text,
        ])
    if "APPROVE" not in verdict_line:
        return GateVerdict(ok=False, lines=[
            f"✗ {gate.label}: no explicit verdict on the first line",
            text,
        ])
    lines = [passed(f"{gate.label}: approved", started)]
    rest = [ln for ln in text.strip().splitlines() if ln != verdict_line]
    if any(line.strip() for line in rest):
        lines.append("\n".join(rest).strip())
    return GateVerdict(ok=True, lines=lines)


def _verdict_line(text: str) -> str:
    lines = text.strip().splitlines()
    return next((ln for ln in lines if ln.lstrip("# ").startswith("Verdict:")), lines[0] if lines else "")


async def _review_prompt(gate: AgenticReview, req: LandRequest) -> str:
    merge = await asyncio.to_thread(
        inspect_merge, req.slot.host_repo, req.candidate,
        target_branch=req.slot.base_branch, root_branch=req.session.base_branch,
    )
    sections = [
        "Review this merge candidate before it lands on "
        f"`{req.slot.base_branch}` ({req.slot.workdir}). You are a landing gate: end "
        "the FIRST line of your conclusion with exactly APPROVE or "
        "REQUEST_CHANGES, then explain. Approve-with-nits is APPROVE plus "
        "notes.",
    ]
    if gate.focus.strip():
        sections.append(f"## Focus\n\n{gate.focus.strip()}")
    if req.description:
        sections.append(f"## Author's description\n\n{req.description}")
    body = await (_merge_sections(req, merge) if merge else _range_sections(req))
    return "\n\n".join(sections + body)


async def _range_sections(req: LandRequest) -> list[str]:
    span = f"{req.base_sha}..{req.candidate}"
    stat = await git_checked(req.slot.host_repo, "diff", "--stat", span)
    diff = await git_checked(req.slot.host_repo, "diff", span)
    return [
        f"Proposed squash message:\n\n```\n{req.message}\n```",
        f"## Changed files\n\n```\n{stat.strip()}\n```",
        _diff_section(diff, req, "git diff FETCH_HEAD^...FETCH_HEAD"),
    ]


async def _merge_sections(req: LandRequest, merge: MergeInfo) -> list[str]:
    span = f"{req.base_sha}..{merge.parents[1]}"
    log = await git_checked(req.slot.host_repo, "log", "--oneline", "--no-decorate", span)
    commits = [ln for ln in log.splitlines() if ln.strip()]
    shown = commits[:MAX_LISTED_MERGE_COMMITS]
    if len(commits) > len(shown):
        shown.append(f"… and {len(commits) - len(shown)} more")
    sections = [
        f"Merge commit message:\n\n```\n{req.message}\n```",
        f"## Merged commits ({len(commits)} from `{merge.merged_from}`)\n\n```\n"
        + "\n".join(shown) + "\n```",
    ]
    if merge.clean:
        sections.append(
            f"## Conflict resolutions\n\n{clean_merge_summary(merge, len(commits))}. "
            "The merged commits were reviewed when they landed on "
            f"`{merge.merged_from}`; only the merge itself is under review. "
            "The full range diff, if you want it: "
            f"`git diff FETCH_HEAD^1 FETCH_HEAD` after `git fetch origin {req.candidate_ref}`."
        )
        return sections
    patch = await asyncio.to_thread(combined_patch, req.slot.host_repo, req.candidate)
    sections.append(
        "## Conflict resolutions\n\nCombined diff of the merge against both parents "
        f"(`{len(merge.conflict_paths)}` files):\n\n```\n"
        + "\n".join(merge.conflict_paths) + "\n```"
    )
    sections.append(_diff_section(patch, req, "git show --cc FETCH_HEAD"))
    return sections


def _diff_section(diff: str, req: LandRequest, command: str) -> str:
    if diff and len(diff) <= MAX_INLINE_REVIEW_DIFF:
        return f"## Diff\n\n```diff\n{diff}\n```"
    return (
        "## Diff\n\nToo large to inline. Fetch the candidate and read "
        f"it yourself:\n\n```\ncd {req.slot.workdir} && "
        f"git fetch origin {req.candidate_ref} && {command}\n```"
    )
