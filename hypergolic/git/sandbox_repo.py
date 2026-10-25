"""Sandbox-owned session repos: the clone-in primitives.

Each session's repos live inside its sandbox: working files on the bind-mounted
workspace dir, the gitdir in a container-only volume at ``/var/git``. The host
repo's gitdir is mounted read-only *at its host-true path* as the clone/fetch
source, so the clone's single alternates line resolves identically in the
container and on the host. Commits leave the sandbox only by pushing to the
session's quarantine repo (:mod:`hypergolic.git.quarantine`): ``origin`` has
split URLs — fetch from the host repo, push to the quarantine.

See docs/sandbox-lifecycle.md for the lifecycle/convergence design.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from hypergolic.git.commands import run_git_command

#: Repo slots a workspace container may carry.
REPO_APP = "app"
REPO_HARNESS = "harness"
REPO_SHARED = "shared"

GITDIR_MOUNT_ROOT = "/var/git"

#: Compose volume key for the per-session gitdir volume. Non-external, so
#: ``compose down -v`` (end-of-life teardown, orphan reaper) removes it with
#: the session; ``remove_gitdir_volume`` covers sandboxes stopped without it.
GITDIR_VOLUME = "hg-gitdir"


def session_gitdir(repo: str) -> str:
    """Container path of the session's gitdir for *repo*."""
    return f"{GITDIR_MOUNT_ROOT}/{repo}.git"


def repo_opens(workdir: str) -> str:
    """Shell condition: the repo at *workdir* opens (a dangling ``.git``
    pointer — its gitdir volume lost — does not)."""
    return f"git -C {shlex.quote(workdir)} rev-parse --git-dir >/dev/null 2>&1"


def hypergolic_ref(project_id: str, branch: str) -> str:
    """Host-side ref namespace for checkpointed session branches."""
    return f"refs/hypergolic/{project_id}/{branch}"


def delete_hypergolic_ref(project_path: str | Path, scope: str, branch: str) -> None:
    """Best-effort removal of a preserved session ref from a host repo."""
    run_git_command(
        "update-ref",
        "-d",
        hypergolic_ref(scope, branch),
        cwd=Path(project_path),
    )


def container_name(compose_project: str, service: str) -> str:
    """Compose v2's deterministic container name for a service replica 1."""
    return f"{compose_project}-{service}-1"


def _config_lines(user_name: str, user_email: str) -> list[str]:
    """Global git config, re-asserted every run: it dies with the container."""
    q = shlex.quote
    return [
        # Bind-mounted dirs are host-owned; in-container git must not balk.
        "git config --global --add safe.directory '*' 2>/dev/null || true",
        f"git config --global user.name {q(user_name)}",
        f"git config --global user.email {q(user_email)}",
    ]


def _heal_lines(workdir: str, src: str, push_url: str) -> list[str]:
    """Re-point an existing clone at the current mount layout. Every value is
    a deterministic function of that layout, so rewriting is always safe."""
    q = shlex.quote
    return [
        f"git -C {q(workdir)} remote set-url origin {q(src)}",
        f"git -C {q(workdir)} remote set-url --push origin {q(push_url)}",
        f'hg_gd="$(git -C {q(workdir)} rev-parse --absolute-git-dir)"',
        f"printf '%s\\n' {q(src + '/objects')} > \"$hg_gd/objects/info/alternates\"",
    ]


def _tracking_lines(workdir: str, branch: str, base_ref: str) -> list[str]:
    """Make ``origin/<branch>`` track *base_ref* when it is not the host's
    ``refs/heads/<branch>`` (a child rooted at its parent's checkpoint).

    Without this ``origin/main`` in a child is the host's real ``main``, not
    the parent branch it lands into. The negative refspec also keeps a push to
    ``main`` from resetting ``origin/main`` to the pushed sha: the land's
    post step sets it to the merge result instead.
    """
    if base_ref == f"refs/heads/{branch}":
        return []
    q = shlex.quote
    key = "remote.origin.fetch"
    return [
        f"git -C {q(workdir)} config --unset-all {key} || true",
        f"git -C {q(workdir)} config --add {key} '+refs/heads/*:refs/remotes/origin/*'",
        f"git -C {q(workdir)} config --add {key} {q(f'^refs/heads/{branch}')}",
        f"git -C {q(workdir)} config --add {key} {q(f'+{base_ref}:refs/remotes/origin/{branch}')}",
    ]


def _verify_lines(workdir: str) -> list[str]:
    """The repo opens and its fetch remote works; under ``set -e``."""
    q = shlex.quote
    return [
        f"git -C {q(workdir)} rev-parse --git-dir >/dev/null",
        f"git -C {q(workdir)} fetch --quiet origin",
    ]


def _hook_lines(workdir: str, gitdir_q: str, pre_commit: str) -> list[str]:
    """``gitdir_q`` is pre-quoted: callers pass a literal path or `"$hg_gd"`
    (set by :func:`_heal_lines` via rev-parse)."""
    hook = shlex.quote(f"#!/bin/sh\ncd {workdir} && exec {pre_commit}\n")
    return [
        f"mkdir -p {gitdir_q}/hooks",
        f"printf '%s' {hook} > {gitdir_q}/hooks/pre-commit",
        f"chmod +x {gitdir_q}/hooks/pre-commit",
    ]


def clone_script(
    *,
    repo: str,
    workdir: str,
    src: str,
    base_ref: str,
    branch: str,
    push_url: str,
    user_name: str = "Hypergolic",
    user_email: str = "agent@hypergolic.local",
    pre_commit: str | None = None,
    pin: str | None = None,
) -> str:
    """Convergent in-container provisioning script for one repo slot: heal
    when the repo opens, rebuild in place when the ``.git`` pointer dangles
    (its gitdir volume died under a surviving workspace), clone when the slot
    is empty; verify in every case.

    ``--shared`` (not ``--reference``: a local clone copies objects anyway)
    records an alternates entry into the read-only host-repo mount, so the
    clone materializes no history. The workspace dir is a host bind mount
    created empty; ``.git`` there becomes a pointer file whose target only
    resolves in the container — host git never opens this repo.

    The checkout is named *branch* — the base branch's own name, so ``git
    push origin main`` / ``git pull`` are the trained-in words — and its
    upstream is *base_ref*, any ref resolvable in the host repo:
    ``refs/heads/main`` for a top-level session, ``refs/hypergolic/...`` for
    a dispatched child branching off its parent's checkpointed tip.

    A *pin* checks the branch out at that sha instead of the fetched tip;
    the sha's objects come straight from the host repo via the alternates
    entry, so an unreachable (GC'd) pin fails the clone visibly.
    """
    gitdir = session_gitdir(repo)
    q = shlex.quote
    tip = q(pin) if pin else "FETCH_HEAD"
    # Split URLs: fetch reads the live host repo, push lands in the
    # session's quarantine, where the pre-receive hook gates landing.
    wiring = [
        f"git -C {q(workdir)} remote set-url --push origin {q(push_url)}",
        f"git -C {q(workdir)} config branch.{q(branch)}.remote origin",
        f"git -C {q(workdir)} config branch.{q(branch)}.merge {q(base_ref)}",
        *_tracking_lines(workdir, branch, base_ref),
    ]
    lines = [
        "set -e",
        *_config_lines(user_name, user_email),
        f"if {repo_opens(workdir)}; then",
        *_heal_lines(workdir, src, push_url),
        f"elif [ -e {q(workdir)}/.git ]; then",
        # Dangling gitdir pointer: the workspace outlived its gitdir volume.
        # Rebuild around the surviving files — mixed reset, never a checkout.
        f"rm -f {q(workdir)}/.git",
        f"git init --quiet --separate-git-dir={q(gitdir)} {q(workdir)}",
        f"git -C {q(workdir)} remote remove origin >/dev/null 2>&1 || true",
        f"git -C {q(workdir)} remote add origin {q(src)}",
        f"printf '%s\\n' {q(src + '/objects')} > {q(gitdir)}/objects/info/alternates",
        f"git -C {q(workdir)} fetch --quiet origin {q(base_ref)}",
        f"git -C {q(workdir)} update-ref refs/heads/{q(branch)} {tip}",
        f"git -C {q(workdir)} symbolic-ref HEAD refs/heads/{q(branch)}",
        f"git -C {q(workdir)} reset --quiet",
        *wiring,
        "else",
        f"git clone --quiet --shared --no-checkout "
        f"--separate-git-dir={q(gitdir)} {q(src)} {q(workdir)}",
        f"git -C {q(workdir)} fetch --quiet origin {q(base_ref)}",
        f"git -C {q(workdir)} checkout --quiet -B {q(branch)} " + tip,
        *wiring,
        "fi",
    ]
    if pre_commit:
        lines += _hook_lines(workdir, q(gitdir), pre_commit)
    lines += _verify_lines(workdir)
    return "\n".join(lines)


def heal_script(
    *,
    workdir: str,
    src: str,
    push_url: str,
    user_name: str = "Hypergolic",
    user_email: str = "agent@hypergolic.local",
    pre_commit: str | None = None,
) -> str:
    """Heal + verify an existing clone without cloning (a missing repo is a
    no-op success: cloning /app needs base-ref resolution the caller owns)."""
    q = shlex.quote
    lines = [
        "set -e",
        *_config_lines(user_name, user_email),
        f"[ -e {q(workdir)}/.git ] || exit 0",
        *_heal_lines(workdir, src, push_url),
    ]
    if pre_commit:
        lines += _hook_lines(workdir, '"$hg_gd"', pre_commit)
    lines += _verify_lines(workdir)
    return "\n".join(lines)
