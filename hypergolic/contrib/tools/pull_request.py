"""GitHub pull requests for branches that already live on the user's machine.

`publish` pushes a *host* branch, exactly as it is, to GitHub and opens a PR,
or updates the branch when its PR already exists. Before approval, `align`
requires the sandbox HEAD to match that branch (fast-forwarding the sandbox
when the host is simply ahead), so what the agent has is what gets published.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import Field

from hypergolic.git.commands import async_run_git_command
from hypergolic.contrib.tools.pull_request_align import align
from hypergolic.harness.primitives.approval import ApprovalContext, ToolApprovalDecision
from hypergolic.harness.primitives.eval_behavior import always_conduct
from hypergolic.harness.primitives.results import InputSchema, ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.tools.approval_view import (
    ApprovalView,
    BadgeBlock,
    MarkdownBlock,
    TextBlock,
)
from hypergolic.tools.subprocess_util import run_subprocess
from hypergolic.commands.argv import positional

Action = Literal["list", "publish", "view"]
PR_FIELDS = "number,title,url,state,isDraft,headRefName,baseRefName,statusCheckRollup,reviewDecision"


class PullRequestInput(InputSchema):
    action: Action
    branch: str | None = Field(
        default=None, description="publish: host branch to push; view: PR number or branch",
    )
    title: str | None = None
    body: str | None = Field(default=None, description="Markdown")
    body_file: str | None = Field(default=None, description="Sandbox path (/app/...) to read the body from")
    base: str | None = Field(default=None, description="PR base; defaults to the repo's default branch")
    draft: bool = True
    reviewer: list[str] = Field(default_factory=list)
    label: list[str] = Field(default_factory=list)
    author: str = Field(default="@me", description="list: filter by author")
    state: Literal["open", "closed", "merged", "all"] = "open"
    limit: int = 20
    search: str | None = Field(default=None, description="list: GitHub search query")


def _fail(text: str) -> ToolResult:
    return ToolResult.text(text, is_error=True)


def _checks(rollup: list[dict] | None) -> str:
    if not rollup:
        return "–"
    outcomes = {(c.get("conclusion") or c.get("state") or "").upper() for c in rollup}
    if outcomes & {"FAILURE", "ERROR", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"}:
        return "✗"
    if outcomes - {"SUCCESS", "NEUTRAL", "SKIPPED"}:
        return "…"
    return "✓"


def _row(pr: dict) -> str:
    draft = " [draft]" if pr.get("isDraft") else ""
    return (
        f"#{pr['number']}  {pr['headRefName']}  {pr['title']}{draft}  "
        f"checks:{_checks(pr.get('statusCheckRollup'))}  {pr['url']}"
    )


async def _gh(cwd: Path, *args: str):
    return await run_subprocess(["gh", *args], cwd=cwd)


async def _list(inp: PullRequestInput, cwd: Path) -> ToolResult:
    args = ["pr", "list", "--author", inp.author, "--state", inp.state,
            "--limit", str(inp.limit), "--json", PR_FIELDS]
    if inp.search:
        args += ["--search", inp.search]
    result = await _gh(cwd, *args)
    if result.returncode != 0:
        return _fail(f"`gh pr list` failed:\n{result.stderr.strip()}")
    prs = json.loads(result.stdout or "[]")
    if not prs:
        return ToolResult.text(f"No {inp.state} PRs by {inp.author}.")
    return ToolResult.text("\n".join(_row(pr) for pr in prs))


async def _view(inp: PullRequestInput, cwd: Path) -> ToolResult:
    if not inp.branch:
        return _fail("view needs a PR number or branch.")
    result = await _gh(cwd, "pr", "view", inp.branch, "--json", PR_FIELDS)
    if result.returncode != 0:
        return _fail(f"`gh pr view` failed:\n{result.stderr.strip()}")
    pr = json.loads(result.stdout)
    return ToolResult.text(
        f"{_row(pr)}\nstate:{pr['state']}  base:{pr['baseRefName']}  "
        f"review:{pr.get('reviewDecision') or '–'}"
    )


async def _open_pr(inp: PullRequestInput, cwd: Path, branch: str) -> ToolResult:
    if not inp.title:
        return _fail("publish needs --title to open a new PR.")
    args = ["pr", "create", "--head", branch, "--title", inp.title, "--body", inp.body or ""]
    if inp.base:
        args += ["--base", inp.base]
    if inp.draft:
        args.append("--draft")
    for r in inp.reviewer:
        args += ["--reviewer", r]
    for lbl in inp.label:
        args += ["--label", lbl]
    result = await _gh(cwd, *args)
    if result.returncode != 0:
        return _fail(
            f"Pushed `{branch}` but `gh pr create` failed:\n"
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return ToolResult.text(f"PR created: {result.stdout.strip()}")


async def _publish(inp: PullRequestInput, cwd: Path) -> ToolResult:
    branch = inp.branch
    assert branch
    push = await async_run_git_command(
        "push", "--force-with-lease", "origin", f"refs/heads/{branch}:refs/heads/{branch}", cwd=cwd,
    )
    if push.returncode != 0:
        return _fail(
            "Push failed (a stale lease means GitHub's branch moved — git_fetch, "
            f"rebase, re-land, retry):\n{push.stderr.strip()}"
        )
    existing = await _gh(cwd, "pr", "list", "--head", branch, "--state", "open", "--json", "number,url")
    open_prs = json.loads(existing.stdout or "[]") if existing.returncode == 0 else []
    if open_prs:
        pr = open_prs[0]
        return ToolResult.text(f"Pushed `{branch}`; updated PR #{pr['number']}: {pr['url']}")
    return await _open_pr(inp, cwd, branch)


async def _run(inp: PullRequestInput, ctx: ToolContext) -> ToolResult:
    cwd = Path(ctx.session.project_path)
    if inp.action == "list":
        return await _list(inp, cwd)
    if inp.action == "view":
        return await _view(inp, cwd)
    return await _publish(inp, cwd)


def _approval(ctx: ApprovalContext) -> ToolApprovalDecision:
    if ctx.input.action == "publish":
        return ToolApprovalDecision(decision="REQUIRE_APPROVAL")
    return ToolApprovalDecision(decision="ALLOW")


pull_request_tool = Tool(
    id="pull_request",
    tags=["pull-request", "pr", "github", "push", "publish", "draft", "remote", "sync-out", "upload"],
    name="Pull Request",
    description=(
        "GitHub PRs for host branches: `list` yours, `view` one, or `publish <branch>` "
        "to push the user's branch (which must match your sandbox HEAD; land first) and open or update a draft PR"
    ),
    input_schema=PullRequestInput,
    argv=positional(
        "action", "branch",
        values={"title", "body", "body_file", "base", "author", "state", "limit", "search"},
        multi={"reviewer", "label"}, negated={"no_draft"}, remap={"no_draft": "draft"},
    ),
    usage=(
        "pull_request list [--author @me] [--state open|closed|merged|all] [--limit 20] [--search Q]\n"
        "pull_request publish <branch> --title T (--body '...' | --body-file /app/PR.md) "
        "[--base B] [--no-draft] [--reviewer U]... [--label L]...\n"
        "pull_request view <number|branch>"
    ),
    run=_run,
    validate_tool_call=align,
    approval=_approval,
    eval_behavior=always_conduct,
    requires_worktree=True,
    approval_view=ApprovalView(
        blocks=[
            TextBlock(field="action", label="Action", mono=True),
            TextBlock(field="branch", label="Branch", mono=True),
            TextBlock(field="base", label="Base", mono=True),
            BadgeBlock(field="draft", label="Draft", tone="info"),
            TextBlock(field="title", label="Title"),
            MarkdownBlock(field="body"),
        ],
        show_raw_json=False,
    ),
)


__all__ = ["pull_request_tool", "PullRequestInput"]
