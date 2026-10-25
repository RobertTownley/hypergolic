"""``/tools`` is the discovery surface, so what is *absent* matters as much as
what is present: no shim means advisory, and a vanished command must lose its
shim rather than linger as a capability the agent will try and fail to use."""

from typing import Any

import pytest

import hypergolic.config.settings as settings
from hypergolic.commands import materialize as mat
from hypergolic.commands.validate import CommandValidationError
from hypergolic.harness.primitives.approval import always
from hypergolic.harness.primitives.results import CommandResult
from hypergolic.harness.primitives.tool import Tool


async def _run(_inp, _ctx):
    return CommandResult(stdout="ok")


def command(cid: str = "probe", **overrides) -> Tool:
    fields: dict[str, Any] = dict(
        id=cid,
        name=cid.title(),
        description=f"Do the {cid} thing.",
        usage=f"{cid} <arg>",
        approval=always("ALLOW"),
        run=_run,
    )
    fields.update(overrides)
    return Tool(**fields)


@pytest.fixture(autouse=True)
def _tools_root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "INTERNALS_DIR", tmp_path)
    mat._FINGERPRINTS.clear()
    yield
    mat._FINGERPRINTS.clear()


def test_invocable_command_gets_a_shim_and_a_readme():
    root = mat.materialize("s1", {"probe": command()})
    shim = root / "bin" / "probe"
    assert shim.is_file() and shim.stat().st_mode & 0o111
    assert "probe <arg>" in (root / "probe" / "README.md").read_text()


def test_advisory_command_gets_docs_and_no_shim():
    root = mat.materialize("s1", {"guide": Tool(id="guide", name="Guide", description="How to")})
    assert (root / "guide" / "README.md").is_file()
    assert not (root / "bin" / "guide").exists()


def test_source_symlink_points_where_the_container_can_read_it():
    root = mat.materialize("s1", {"probe": command()})
    link = root / "probe" / "source"
    assert link.is_symlink()
    target = str(link.readlink())
    assert target.endswith("commands/tests/test_materialize.py")
    assert target.startswith("/")


def test_index_lists_every_command_for_grepping():
    root = mat.materialize("s1", {"a": command("a"), "b": command("b")})
    index = (root / "index.md").read_text()
    assert "a" in index and "b" in index


def test_a_removed_command_loses_its_shim():
    mat.materialize("s1", {"a": command("a"), "b": command("b")})
    root = mat.materialize("s1", {"a": command("a")})
    assert (root / "bin" / "a").exists()
    assert not (root / "bin" / "b").exists()
    assert not (root / "b").exists()


def test_sync_rewrites_only_when_the_command_set_changed():
    commands = {"a": command("a")}
    assert mat.sync("s1", commands) is None
    stamp = (mat.tools_dir("s1") / "bin" / "a").stat().st_mtime_ns
    assert mat.sync("s1", commands) is None
    assert (mat.tools_dir("s1") / "bin" / "a").stat().st_mtime_ns == stamp

    assert mat.sync("s1", {"a": command("a"), "b": command("b")}) is None
    assert (mat.tools_dir("s1") / "bin" / "b").is_file()


def test_sync_regenerates_a_tree_deleted_underneath_it():
    commands = {"a": command("a")}
    mat.sync("s1", commands)
    mat.discard("s1")
    mat.sync("s1", commands)
    assert (mat.tools_dir("s1") / "bin" / "a").is_file()


def test_a_broken_command_set_reports_instead_of_taking_the_turn_down():
    problem = mat.ensure_materialized("s1", {"test": command("test")})
    assert problem is not None and "/tools" in problem
    with pytest.raises(CommandValidationError):
        mat.materialize("s1", {"test": command("test")})


def test_discard_leaves_nothing_behind():
    mat.sync("s1", {"a": command("a")})
    mat.discard("s1")
    assert not mat.tools_dir("s1").exists()
    assert "s1" not in mat._FINGERPRINTS


def test_regeneration_keeps_the_directory_the_container_has_mounted():
    """compose bind-mounts this root, so replacing it would swap the inode and
    leave `/tools` permanently empty inside a container that is already up — in
    exactly the cases the design exists for, like `mcp activate`."""
    root = mat.materialize("s1", {"a": command("a")})
    before = root.stat().st_ino
    again = mat.materialize("s1", {"b": command("b")})
    assert again.stat().st_ino == before
    assert (again / "bin" / "b").is_file()
