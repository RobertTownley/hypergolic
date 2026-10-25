from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from hypergolic.contrib.tools.land.inputs import Target
from hypergolic.contrib.tools.land.target import create_branch
from hypergolic.gates.candidate import resolve_branch
from hypergolic.git.eval_source import set_eval_branch
from hypergolic.git.integrate import advance_branch, checkout_blocker
from hypergolic.git.parent_land import advance_parent, parent_tip, reset_child_onto
from hypergolic.git.sandbox_integrate import reconcile_after_land
from hypergolic.harness.primitives.tool import ToolContext

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Dest:
    """Where a gated candidate lands: a host branch, or a parent's sandbox."""

    advance: Callable[[str, str, list[str]], Awaitable[tuple[bool, str]]]  # (base, candidate, lines)
    tip: Callable[[], Awaitable[str | None]]
    post: Callable[[str, str], Awaitable[None]]  # (pushed sha, landed commit)
    pull_hint: str
    blocker: Callable[[str, str], Awaitable[str | None]] | None = None


def host_dest(ctx: ToolContext, project, slot, target: Target) -> Dest:
    host = slot.host_repo

    async def advance(base_sha: str, candidate: str, lines: list[str]) -> tuple[bool, str]:
        if target.create and await resolve_branch(host, slot.base_branch) is None:
            await create_branch(host, slot.base_branch, target)
            lines.append(f"created {slot.base_branch} at {base_sha[:8]}")
        return await advance_branch(
            base_branch=slot.base_branch, old_base_sha=base_sha, new_commit=candidate, cwd=host,
        )

    async def post(pushed_sha: str, _landed: str) -> None:
        await post_land(ctx.session, project, slot, pushed_sha)

    async def blocker(base_sha: str, candidate: str) -> str | None:
        return await checkout_blocker(
            base_branch=slot.base_branch, base_sha=base_sha, new_commit=candidate, cwd=host,
        )

    return Dest(
        advance=advance, tip=lambda: resolve_branch(host, slot.base_branch), post=post,
        pull_hint=f"git pull origin {slot.base_branch}", blocker=blocker,
    )


def parent_dest(ctx: ToolContext, project, parent, branch: str) -> Dest:
    async def advance(base_sha: str, candidate: str, _lines: list[str]) -> tuple[bool, str]:
        return await advance_parent(parent, project, old_sha=base_sha, new_commit=candidate)

    async def post(pushed_sha: str, landed: str) -> None:
        try:
            # Refresh the parent's checkpoint first, so the child's next
            # `git fetch` agrees with the origin/<branch> set below.
            await parent_tip(parent, project)
        except Exception:
            logger.warning("post-land parent checkpoint failed", exc_info=True)
        if ctx.session.conducted_by:
            try:
                await set_eval_branch(ctx.session.id, branch, landed)
            except Exception:
                logger.warning("post-land eval source update failed", exc_info=True)
        try:
            await reset_child_onto(
                ctx.session, project, pushed_sha=pushed_sha, new_tip=landed, branch=branch,
            )
        except Exception:
            logger.warning("post-land reconcile failed", exc_info=True)

    return Dest(
        advance=advance, tip=lambda: parent_tip(parent, project), post=post, pull_hint="git pull",
    )


async def post_land(session, project, slot, landed_sha: str) -> None:
    """Move the agent's checkout onto the landed tip (best-effort)."""
    try:
        await reconcile_after_land(session, project, slot, landed_sha)
    except Exception:
        logger.warning("post-land reconcile failed", exc_info=True)
