"""Tests for hypergolic.cli.init_cmd."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer

import hypergolic.contrib as contrib_pkg
from hypergolic.cli.init_cmd import (
    _REQUIRED_GITIGNORE_ENTRIES,
    generate_pyproject,
    init,
    init_impl,
    setup_gitignore,
)


def _make_contrib(contrib_dir: Path, template: bool = True) -> None:
    contrib_dir.mkdir(parents=True, exist_ok=True)
    if template:
        (contrib_dir / "main_template.py").write_text("# template\n")
    (contrib_dir / ".gitignore").write_text("__pycache__/\n")


def _fake_run(dirty: bool, uv_ok: bool):
    def run(argv, **_):
        if argv[:2] == ["git", "diff"]:
            return MagicMock(returncode=1 if dirty else 0)
        if argv[:2] == ["uv", "sync"]:
            return MagicMock(returncode=0 if uv_ok else 1, stderr="boom")
        return MagicMock(returncode=0)
    return run


def _init(
    tmp_path: Path, *, root_exists=False, confirm=True, template=True,
    shell_configs=(), dirty=True, uv_ok=True, git_repo=False,
):
    root = tmp_path / "harness"
    if root_exists or git_repo:
        root.mkdir()
    if git_repo:
        (root / ".git").mkdir()
    contrib_dir = tmp_path / "contrib_src"
    _make_contrib(contrib_dir, template=template)
    with (
        patch("hypergolic.cli.init_cmd.subprocess.run", side_effect=_fake_run(dirty, uv_ok)) as run,
        patch("typer.confirm", return_value=confirm) as ask,
    ):
        init_impl(root_dir=root, contrib_dir=contrib_dir, shell_configs=list(shell_configs))
    argvs = [c.args[0] for c in run.call_args_list]
    return root, argvs, ask


def test_setup_gitignore_copies_from_contrib(tmp_path):
    root = tmp_path / "home"
    root.mkdir()
    contrib = root / "contrib"
    contrib.mkdir()
    (contrib / ".gitignore").write_text("*.pyc\nmcp_tokens/\n")

    setup_gitignore(root_dir=root, contrib_dir=contrib)

    assert (root / ".gitignore").read_text() == "*.pyc\nmcp_tokens/\n"


def test_setup_gitignore_noop_when_no_contrib(tmp_path):
    root = tmp_path / "home"
    root.mkdir()
    setup_gitignore(root_dir=root, contrib_dir=tmp_path / "nonexistent")
    assert not (root / ".gitignore").exists()


def test_setup_gitignore_appends_missing_entries_once(tmp_path):
    root = tmp_path / "home"
    root.mkdir()
    (root / ".gitignore").write_text("*.pyc\n")

    setup_gitignore(root_dir=root)

    content = (root / ".gitignore").read_text()
    for entry in _REQUIRED_GITIGNORE_ENTRIES:
        assert entry in content
    assert "# Added by hypergolic update" in content
    # Worktrees must stay ignored so the My Harness project doesn't show
    # them as untracked.
    assert "worktrees/" in _REQUIRED_GITIGNORE_ENTRIES

    setup_gitignore(root_dir=root)
    assert (root / ".gitignore").read_text() == content


def test_generate_pyproject_creates_new(tmp_path):
    with patch.dict("os.environ", {}, clear=True):
        generate_pyproject(root_dir=tmp_path)

    content = (tmp_path / "pyproject.toml").read_text()
    assert "my-hypergolic" in content
    assert "hypergolic>=" in content


def test_generate_pyproject_updates_existing(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "my-hypergolic"\ndependencies = ["hypergolic>=0.1.0"]\n'
    )

    with patch.dict("os.environ", {}, clear=True):
        generate_pyproject(root_dir=tmp_path)

    content = (tmp_path / "pyproject.toml").read_text()
    assert "hypergolic>=0.1.0" not in content or content.count("hypergolic>=") == 1


@pytest.mark.parametrize("value", ["1", "true", "YES"])
def test_generate_pyproject_dev_mode(tmp_path, value):
    with patch.dict("os.environ", {"HYPERGOLIC_DEV_MODE": value}):
        generate_pyproject(root_dir=tmp_path)

    content = (tmp_path / "pyproject.toml").read_text()
    assert "editable = true" in content
    assert "[tool.uv.sources]" in content


def test_generate_pyproject_ignores_unknown_dev_mode_value(tmp_path):
    with patch.dict("os.environ", {"HYPERGOLIC_DEV_MODE": "nope"}):
        generate_pyproject(root_dir=tmp_path)

    assert "[tool.uv.sources]" not in (tmp_path / "pyproject.toml").read_text()


def test_init_fresh_directory(tmp_path):
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("# shell\n")

    root, argvs, _ = _init(tmp_path, shell_configs=[zshrc])

    assert (root / "prompts" / "roles").is_dir()
    assert (root / "prompts" / "skills").is_dir()
    assert (root / "projects").is_dir()
    assert (root / "main.py").exists()
    assert not (root / "contrib").exists()
    assert (root / ".gitignore").exists()
    assert (root / "pyproject.toml").exists()
    assert "alias h=" in zshrc.read_text()
    assert ["uv", "sync"] in argvs


def test_init_existing_directory_confirm_yes(tmp_path):
    root, _, _ = _init(tmp_path, root_exists=True)
    assert (root / "main.py").exists()
    assert not (root / "contrib").exists()


def test_init_existing_directory_confirm_no(tmp_path):
    with pytest.raises(typer.Exit):
        _init(tmp_path, root_exists=True, confirm=False)


def test_init_keeps_existing_main_py(tmp_path):
    root = tmp_path / "harness"
    root.mkdir()
    (root / "main.py").write_text("# existing\n")

    _init(tmp_path)

    assert (root / "main.py").read_text() == "# existing\n"


def test_init_without_template_writes_no_main_py(tmp_path):
    root, _, _ = _init(tmp_path, template=False)
    assert not (root / "main.py").exists()


def test_init_git_inits_and_commits(tmp_path):
    _, argvs, _ = _init(tmp_path)
    git = [a for a in argvs if a[0] == "git"]
    assert git[0] == ["git", "init"]
    assert git[-1][:3] == ["git", "commit", "-m"]


def test_init_reuses_existing_git_repo(tmp_path):
    _, argvs, _ = _init(tmp_path, git_repo=True)
    assert ["git", "init"] not in argvs


def test_init_makes_no_commit_when_clean(tmp_path):
    _, argvs, _ = _init(tmp_path, dirty=False)
    assert not any(a[:2] == ["git", "commit"] for a in argvs)


def test_init_survives_uv_sync_failure(tmp_path):
    root, _, _ = _init(tmp_path, uv_ok=False)
    assert (root / "pyproject.toml").exists()


@pytest.mark.parametrize("confirm", [True, False], ids=["confirmed", "declined"])
def test_init_adds_shell_alias(tmp_path, confirm):
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("# existing config\n")

    _init(tmp_path, confirm=confirm, shell_configs=[zshrc])

    content = zshrc.read_text()
    assert ("alias h=" in content) is confirm
    assert ("# Hypergolic" in content) is confirm


@pytest.mark.parametrize("confirm", [True, False], ids=["confirmed", "declined"])
def test_init_updates_existing_shell_alias(tmp_path, confirm):
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text("alias h='old value'\n")

    root, _, _ = _init(tmp_path, confirm=confirm, shell_configs=[zshrc])

    content = zshrc.read_text()
    assert ("old value" in content) is not confirm
    if confirm:
        assert f"cd {root} && uv run main.py" in content


def test_init_leaves_current_alias_alone(tmp_path):
    root = tmp_path / "harness"
    alias_line = f"alias h='(cd {root} && uv run main.py)'"
    zshrc = tmp_path / ".zshrc"
    zshrc.write_text(f"{alias_line}\n")

    _, _, ask = _init(tmp_path, shell_configs=[zshrc])

    assert all("alias" not in str(c.args[0]) for c in ask.call_args_list)
    assert zshrc.read_text() == f"{alias_line}\n"


def test_init_without_shell_config_still_completes(tmp_path):
    root, _, _ = _init(tmp_path, shell_configs=[tmp_path / ".zshrc"])
    assert (root / "main.py").exists()


def test_init_alias_goes_to_first_existing_config(tmp_path):
    zshrc = tmp_path / ".zshrc"
    bashrc = tmp_path / ".bashrc"
    zshrc.write_text("# zsh\n")
    bashrc.write_text("# bash\n")

    _init(tmp_path, shell_configs=[zshrc, bashrc])

    assert "alias h=" in zshrc.read_text()
    assert "alias h=" not in bashrc.read_text()


def test_init_targets_the_harness_dir_and_package_contrib():
    with patch("hypergolic.cli.init_cmd.init_impl") as mock_impl:
        init()
    kwargs = mock_impl.call_args.kwargs
    assert kwargs["contrib_dir"] == Path(contrib_pkg.__file__).parent
    assert [c.name for c in kwargs["shell_configs"]] == [".zshrc", ".bashrc"]


def test_main_template_uses_defaults():
    """The scaffolded main.py uses use_defaults() and no longer imports copied contrib."""
    template = (Path(contrib_pkg.__file__).parent / "main_template.py").read_text()
    assert "use_defaults()" in template
    assert "from contrib." not in template
