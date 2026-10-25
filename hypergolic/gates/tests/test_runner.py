from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from hypergolic.dispatch.state import DispatchResult
from hypergolic.gates.model import AgenticReview, Check, Parallel
from hypergolic.gates.request import LandRequest
from hypergolic.gates.runner import run_pipeline
from hypergolic.git.sandbox_integrate import RepoSlot, SandboxGitError
from tests._factories import build_session
from tests.helpers.git import FakeGit


def _request(host_repo: Path = Path("/tmp/p")) -> LandRequest:
    from tests.conftest import make_project
    from hypergolic.harness.app.state import get_app

    make_project("proj", "P", str(host_repo))
    session = build_session(sid="R1", project_id="proj", project_path=str(host_repo))
    project = get_app().find_project("proj")
    assert project is not None
    slot = RepoSlot(
        repo="app", workdir="/app", host_repo=host_repo, base_branch="main",
        session_branch="main-R1", ref_scope="proj",
    )
    return LandRequest(
        session=session, project=project, slot=slot, base_sha="b" * 40,
        candidate="c" * 40, candidate_ref="refs/hypergolic/proj/main-R1-candidate",
        message="work", broadcast=AsyncMock(),
    )


@pytest.fixture
def stub_prompt():
    with patch("hypergolic.gates.review._review_prompt", new=AsyncMock(return_value="PROMPT")):
        yield


async def test_check_passes_and_reports_duration():
    req = _request()
    with patch(
        "hypergolic.git.sandbox_integrate.exec_repo_git", new=AsyncMock(return_value=""),
    ) as ex:
        verdict = await run_pipeline([Check(name="Tests", cmd="pytest -q")], req)
    assert verdict.ok
    assert verdict.lines[0].startswith("✓ Tests (")
    script = ex.call_args[0][2]
    assert "git checkout --quiet FETCH_HEAD" in script
    assert req.candidate_ref in script
    assert "pytest -q" in script


async def test_check_failure_carries_output_tail():
    req = _request()
    with patch(
        "hypergolic.git.sandbox_integrate.exec_repo_git",
        new=AsyncMock(side_effect=SandboxGitError("assert 1 == 2\n1 failed")),
    ):
        verdict = await run_pipeline([Check(name="Tests", cmd="pytest")], req)
    assert not verdict.ok
    assert verdict.lines[0] == "✗ Tests"
    assert "1 failed" in verdict.lines[1]


async def test_parallel_runs_all_and_fails_if_any_fails():
    req = _request()
    calls = []

    async def fake_exec(session, project, script, timeout=0):
        calls.append(script)
        if "lint" in script:
            raise SandboxGitError("nope")
        return ""

    with patch("hypergolic.git.sandbox_integrate.exec_repo_git", new=fake_exec):
        verdict = await run_pipeline([Parallel(
            Check(name="Tests", cmd="pytest"), Check(name="Lint", cmd="lint ."),
        )], req)
    assert not verdict.ok and len(calls) == 2


@pytest.mark.usefixtures("stub_prompt")
async def test_agentic_review_approve_and_request_changes():
    req = _request()

    def reviewer(conclusion: str):
        return patch(
            "hypergolic.dispatch.runner.dispatch",
            new=AsyncMock(return_value=DispatchResult(outcome="success", conclusion=conclusion)),
        )

    with reviewer("APPROVE\nnice work"):
        verdict = await run_pipeline([AgenticReview()], req)
    assert verdict.ok
    assert "agentic review: approved" in verdict.lines[0]
    assert "nice work" in verdict.lines[1]

    with reviewer("REQUEST_CHANGES\nretry loses the original exception"):
        verdict = await run_pipeline([AgenticReview()], req)
    assert not verdict.ok
    assert "requesting changes" in verdict.lines[0]
    assert "original exception" in verdict.lines[1]

    with reviewer("looks fine I guess"):
        verdict = await run_pipeline([AgenticReview()], req)
    assert not verdict.ok and "no explicit verdict" in verdict.lines[0]

    with reviewer("Verdict stable.\n\n## Verdict: APPROVE\n\n## Summary\nfine"):
        verdict = await run_pipeline([AgenticReview()], req)
    assert verdict.ok and "fine" in verdict.lines[1]


@pytest.mark.usefixtures("stub_prompt")
async def test_agentic_review_auto_concluded_verdict_read_from_reply_text():
    req = _request()
    result = DispatchResult(
        outcome="success",
        conclusion=(
            "Child session (X) ended its turn without calling conclude. "
            "Final message content:\nVerdict: APPROVE\nnice work"
        ),
        auto_concluded=True,
        reply_text="Verdict: APPROVE\nnice work",
    )
    with patch("hypergolic.dispatch.runner.dispatch", new=AsyncMock(return_value=result)):
        verdict = await run_pipeline([AgenticReview()], req)
    assert verdict.ok
    assert "agentic review: approved" in verdict.lines[0]
    assert "nice work" in verdict.lines[1]


async def test_agentic_review_prompt_carries_diff_and_verdict_contract():
    req = _request()
    seen = {}

    async def fake_dispatch(**kwargs):
        seen["prompt"] = kwargs["content_blocks"][0]["text"]
        return DispatchResult(outcome="success", conclusion="APPROVE")

    git = FakeGit({("diff", "--stat"): " w.txt | 1 +", ("diff",): "+w\n"})
    with (
        patch("hypergolic.gates.review.inspect_merge", return_value=None),
        patch("hypergolic.gates.review.git_checked", new=git),
        patch("hypergolic.dispatch.runner.dispatch", new=fake_dispatch),
    ):
        verdict = await run_pipeline([AgenticReview(focus="watch error paths")], req)
    assert verdict.ok
    assert "APPROVE or REQUEST_CHANGES" in seen["prompt"]
    assert "w.txt" in seen["prompt"]
    assert "watch error paths" in seen["prompt"]


async def test_user_approval_carries_the_candidate_span():
    from types import SimpleNamespace

    from hypergolic.gates.model import UserApproval
    from hypergolic.tools.approval import ApprovalResponse

    req = _request()
    seen = {}

    async def cb(request):
        seen["request"] = request
        return ApprovalResponse(approved=True)

    with patch(
        "hypergolic.gates.user_approval.approval_bus.channel",
        return_value=SimpleNamespace(callback=cb),
    ), patch("hypergolic.gates.user_approval.record_approval"):
        verdict = await run_pipeline([UserApproval()], req)
    assert verdict.ok
    args = seen["request"].tool_input["arguments"]
    assert args["sha"] == req.candidate
    assert args["base_sha"] == req.base_sha
    assert args["branch"] == req.slot.base_branch


def _merge_request(repo: Path, *, conflict: bool) -> LandRequest:
    from tests.helpers.git import sync_merge

    pr_tip, merge = sync_merge(repo, conflict=conflict)
    req = _request(repo)
    return replace(req, slot=replace(req.slot, base_branch="pr"),
                   base_sha=pr_tip, candidate=merge, message="Merge main into pr")


async def _prompt_for(req: LandRequest) -> str:
    seen = {}

    async def fake_dispatch(**kwargs):
        seen["prompt"] = kwargs["content_blocks"][0]["text"]
        return DispatchResult(outcome="success", conclusion="APPROVE")

    with patch("hypergolic.dispatch.runner.dispatch", new=fake_dispatch):
        assert (await run_pipeline([AgenticReview()], req)).ok
    return seen["prompt"]


@pytest.mark.timeout(10)
async def test_clean_merge_prompt_says_so_and_lists_merged_commits(repo: Path):
    prompt = await _prompt_for(_merge_request(repo, conflict=False))
    assert "Clean merge of 2 commits from main; no conflict resolutions" in prompt
    assert "Merged commits (2 from `main`)" in prompt
    assert "main one" in prompt and "main two" in prompt
    assert "Merge commit message:" in prompt
    assert "squash" not in prompt
    assert "m1.txt" not in prompt


@pytest.mark.timeout(10)
async def test_conflicting_merge_prompt_carries_only_the_combined_diff(repo: Path):
    prompt = await _prompt_for(_merge_request(repo, conflict=True))
    assert "Clean merge" not in prompt
    assert "diff --cc f.txt" in prompt
    assert "++resolved" in prompt
    assert "m1.txt" not in prompt
