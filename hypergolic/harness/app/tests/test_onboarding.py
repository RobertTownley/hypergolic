"""Tests for hypergolic.harness.app.onboarding."""

from unittest.mock import patch


from hypergolic.harness.app.onboarding import (
    get_builtin_harness_project,
    harness_prompt_fn,
)
from hypergolic.harness.app.core import App
from hypergolic.harness.project import Project
from hypergolic.harness.app.onboarding import PROMPTS_DIR


def test_harness_prompt_fn_no_user_projects_uses_onboarding(tmp_path):
    onboarding = tmp_path / "onboarding.md"
    onboarding.write_text("Welcome to onboarding!")
    app = App()
    app.register_project(Project(id="harness", name="Harness", description="d", git_root=str(tmp_path)))
    with patch("hypergolic.harness.app.onboarding.PROMPTS_DIR", tmp_path):
        result = harness_prompt_fn(app)
    assert result == "Welcome to onboarding!"


def test_harness_prompt_fn_with_user_projects_uses_harness_md(tmp_path):
    harness_md = tmp_path / "harness.md"
    harness_md.write_text("Harness prompt content.")
    app = App()
    app.register_project(Project(id="my-project", name="My Project", description="d", git_root=str(tmp_path)))
    with patch("hypergolic.harness.app.onboarding.PROMPTS_DIR", tmp_path):
        result = harness_prompt_fn(app)
    assert result == "Harness prompt content."


def test_harness_prompt_fn_file_not_found_returns_empty(tmp_path):
    app = App()
    with patch("hypergolic.harness.app.onboarding.PROMPTS_DIR", tmp_path):
        result = harness_prompt_fn(app)
    assert result == ""


def test_harness_prompt_fn_ignores_harness_project_for_user_check(tmp_path):
    onboarding = tmp_path / "onboarding.md"
    onboarding.write_text("onboarding")
    app = App()
    app.register_project(Project(id="harness", name="Harness", description="d", git_root=str(tmp_path)))
    with patch("hypergolic.harness.app.onboarding.PROMPTS_DIR", tmp_path):
        result = harness_prompt_fn(app)
    assert result == "onboarding"


def test_harness_prompt_fn_both_user_and_harness_projects(tmp_path):
    harness_md = tmp_path / "harness.md"
    harness_md.write_text("For users")
    app = App()
    app.register_project(Project(id="harness", name="Harness", description="d", git_root=str(tmp_path)))
    app.register_project(Project(id="user-proj", name="User Proj", description="d", git_root=str(tmp_path)))
    with patch("hypergolic.harness.app.onboarding.PROMPTS_DIR", tmp_path):
        result = harness_prompt_fn(app)
    assert result == "For users"


def test_get_builtin_harness_project_returns_project():
    proj = get_builtin_harness_project()
    assert isinstance(proj, Project)
    assert proj.id == "harness"
    assert proj.name == "My Harness"
    assert ".hypergolic" in proj.git_root


def test_get_builtin_harness_project_has_prompt_fn():
    proj = get_builtin_harness_project()
    assert proj.prompt_fn is not None
    assert callable(proj.prompt_fn)


def test_get_builtin_harness_project_prompt_fn_is_harness_prompt_fn():
    proj = get_builtin_harness_project()
    assert proj.prompt_fn is harness_prompt_fn


def test_get_builtin_harness_project_description_mentions_configuration():
    proj = get_builtin_harness_project()
    assert "harness" in proj.description.lower() or "configuration" in proj.description.lower()


def test_prompts_dir_resolves_to_packaged_prompts():
    """Built-in harness prompts ship with the package; the un-patched
    PROMPTS_DIR must point at real, existing files (they are no longer copied
    into ~/.hypergolic). Guards against regressing to the old contrib-copy path."""

    assert (PROMPTS_DIR / "onboarding.md").is_file()
    assert (PROMPTS_DIR / "harness.md").is_file()


def test_harness_prompt_fn_reads_real_packaged_prompt():
    """With no patching, an onboarding app gets non-empty prompt content read
    straight from the package."""
    app = App()
    result = harness_prompt_fn(app)
    assert result != ""
