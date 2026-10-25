"""Repo pins: per-slot sha selection and creation-time sha recording.

A pin fixes a repo slot's in-sandbox checkout to a specific sha; unpinned
slots get the branch tip as usual. Whatever is checked out, the resolved sha
of every slot is recorded on the session row at creation — that record is
what makes any past session replayable.
"""
from __future__ import annotations

import re
from pathlib import Path

import hypergolic.config.settings as config
from hypergolic.git.commands import run_git_command
from hypergolic.git.sandbox_repo import REPO_APP, REPO_HARNESS, REPO_SHARED
from hypergolic.sandbox.shared import shared_dir

REPO_SLOTS = (REPO_APP, REPO_HARNESS, REPO_SHARED)

RepoPins = dict[str, str]


_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")


def validate_pins(pins: RepoPins | None) -> RepoPins:
    """Pins are full 40-hex shas — refs would corrupt the repo_shas record."""
    if not pins:
        return {}
    unknown = set(pins) - set(REPO_SLOTS)
    if unknown:
        raise ValueError(f"Unknown repo slot(s) in pins: {sorted(unknown)}")
    bad = [f"{k}={v!r}" for k, v in pins.items() if not _SHA_RE.match(v)]
    if bad:
        raise ValueError(f"Pins must be full 40-hex shas: {', '.join(bad)}")
    return dict(pins)


def _rev_parse(repo: Path, ref: str) -> str | None:
    if not (repo / ".git").exists():
        return None
    result = run_git_command("rev-parse", "--verify", "--quiet", ref, cwd=repo)
    sha = result.stdout.strip()
    return sha if result.returncode == 0 and sha else None


def resolve_repo_shas(
    project_id: str, project_path: str, base_branch: str, pins: RepoPins,
) -> dict[str, str | None]:
    """Resolved sha per slot: the pin when given, else the current tip.

    A slot resolves to None when no tip exists (base branch not on the host —
    dispatched children — or the slot isn't git-controlled).
    """
    return {
        REPO_APP: pins.get(REPO_APP)
        or _rev_parse(Path(project_path), f"refs/heads/{base_branch}"),
        REPO_HARNESS: pins.get(REPO_HARNESS)
        or _rev_parse(config.HARNESS_DIR, "HEAD"),
        REPO_SHARED: pins.get(REPO_SHARED)
        or _rev_parse(shared_dir(project_id), "refs/heads/main"),
    }


def _slot_repo(slot: str, project_id: str, project_path: str) -> Path:
    if slot == REPO_APP:
        return Path(project_path)
    if slot == REPO_HARNESS:
        return config.HARNESS_DIR
    return shared_dir(project_id)


def resolve_pin_refs(
    refs: dict[str, str], project_id: str, project_path: str,
) -> RepoPins:
    """Turn per-slot refs (branch, tag, short sha) into full-sha pins."""
    unknown = set(refs) - set(REPO_SLOTS)
    if unknown:
        raise ValueError(f"Unknown repo slot(s): {sorted(unknown)}")
    pins: RepoPins = {}
    for slot, ref in refs.items():
        sha = _rev_parse(_slot_repo(slot, project_id, project_path), f"{ref}^{{commit}}")
        if sha is None:
            raise ValueError(f"{slot}: cannot resolve {ref!r}")
        pins[slot] = sha
    return validate_pins(pins)
