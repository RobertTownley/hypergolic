from __future__ import annotations

import shlex
import time

from hypergolic.gates.model import Check
from hypergolic.gates.request import GateVerdict, LandRequest, passed

FAIL_TAIL_CHARS = 1_500


async def run_check(gate: Check, req: LandRequest) -> GateVerdict:
    """Run the command in a fresh in-sandbox checkout of the candidate.

    The checkout is cloned inside the session's workspace container — same
    image and dependencies as the agent's own environment, torn down with the
    session — but never *is* the agent's worktree, so local state can't
    invalidate the check.
    """
    from hypergolic.git.sandbox_integrate import GIT_EXEC_TIMEOUT, exec_repo_git

    exports = "".join(
        f"export {k}={shlex.quote(v)}\n" for k, v in gate.env.items()
    )
    script = (
        "set -e\n"
        'd=$(mktemp -d)\n'
        'trap \'rm -rf "$d"\' EXIT\n'
        f"git clone --quiet --shared --no-checkout {shlex.quote(str(req.slot.host_repo / '.git'))} \"$d\"\n"
        'cd "$d"\n'
        f"git fetch --quiet origin {req.candidate_ref}\n"
        "git checkout --quiet FETCH_HEAD\n"
        f"{exports}"
        f"timeout {gate.timeout} sh -c {shlex.quote(gate.cmd)} 2>&1"
    )
    started = time.monotonic()
    try:
        await exec_repo_git(
            req.session, req.project, script,
            timeout=max(GIT_EXEC_TIMEOUT, gate.timeout + 60),
        )
    except Exception as exc:
        tail = str(exc)[-FAIL_TAIL_CHARS:]
        return GateVerdict(ok=False, lines=[f"✗ {gate.name}", tail])
    return GateVerdict(ok=True, lines=[passed(gate.name, started)])
