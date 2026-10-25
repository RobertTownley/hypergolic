from pathlib import Path

import pytest

from hypergolic.sessions.pins import resolve_repo_shas, validate_pins
from tests.helpers.git import run_git


def test_validate_pins_rejects_unknown_slots():
    with pytest.raises(ValueError, match="egress"):
        validate_pins({"egress": "x"})
    assert validate_pins(None) == {}
    assert validate_pins({"app": "a" * 40}) == {"app": "a" * 40}
    with pytest.raises(ValueError, match="40-hex"):
        validate_pins({"app": "main"})


def test_resolve_prefers_pins_and_falls_back_to_tips(
    repo: Path, monkeypatch, tmp_path
):
    tip = run_git(repo, "rev-parse", "refs/heads/main").stdout.strip()
    monkeypatch.setattr(
        "hypergolic.sessions.pins.config.HARNESS_DIR", tmp_path / "noharness"
    )
    monkeypatch.setattr(
        "hypergolic.sessions.pins.shared_dir", lambda pid: tmp_path / "noshared"
    )
    shas = resolve_repo_shas("p", str(repo), "main", {"harness": "d" * 40})
    assert shas == {"app": tip, "harness": "d" * 40, "shared": None}


def test_resolve_none_when_base_branch_not_on_host(repo: Path, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "hypergolic.sessions.pins.config.HARNESS_DIR", tmp_path / "noharness"
    )
    monkeypatch.setattr(
        "hypergolic.sessions.pins.shared_dir", lambda pid: tmp_path / "noshared"
    )
    shas = resolve_repo_shas("p", str(repo), "main-CHILDID", {})
    assert shas["app"] is None
