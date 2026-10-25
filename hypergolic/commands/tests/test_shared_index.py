"""What a past session left in /shared, read back as something searchable."""

from pathlib import Path

from hypergolic.commands.search import search
from hypergolic.commands.shared_index import as_command, scripts


def write(root: Path, name: str, text: str) -> Path:
    path = root / name
    path.write_text(text)
    return path


def test_a_python_header_survives_a_shebang_and_a_uv_script_block(tmp_path):
    write(
        tmp_path,
        "seed.py",
        '#!/usr/bin/env -S uv run\n'
        '# /// script\n# requires-python = ">=3.11"\n# ///\n'
        '"""Seed the staging database.\n\nTakes a snapshot id.\n"""\n',
    )
    (script,) = scripts(tmp_path)
    assert script.summary == "Seed the staging database."
    assert "snapshot id" in script.body
    assert script.run == "uv run /shared/seed.py"


def test_a_shell_script_is_described_by_its_leading_comments(tmp_path):
    write(tmp_path, "probe.sh", "#!/bin/bash\n# Time each debian mirror.\n# tags: mirror, apt\ncurl x\n")
    (script,) = scripts(tmp_path)
    assert script.summary == "Time each debian mirror."
    assert script.tags == ["mirror", "apt"]
    assert script.run == "bash /shared/probe.sh"


def test_a_markdown_note_is_indexed_by_its_heading(tmp_path):
    write(tmp_path, "proxy.md", "# Installing deps behind the proxy\n\nRewrite the lock.\n")
    (script,) = scripts(tmp_path)
    assert script.summary == "Installing deps behind the proxy"
    assert script.run == "cat /shared/proxy.md"


def test_exhaust_is_not_capability(tmp_path):
    for name in ("build.log", "Dockerfile.bak", ".hidden.sh"):
        write(tmp_path, name, "# noise\n")
    (tmp_path / "subdir").mkdir()
    assert scripts(tmp_path) == []


def test_a_headerless_script_says_so_and_is_still_findable_by_its_contents(tmp_path):
    """Most of what accumulates in /shared has no header; searching the body is
    what keeps those reachable, while the description states the gap."""
    write(tmp_path, "node_ver.sh", "#!/bin/bash\ndocker run --rm image node --version\n")
    command = as_command(scripts(tmp_path)[0])
    assert "no header comment" in command.description
    assert [m.command.id for m in search([command], "which node version")] == ["node_ver.sh"]


def document(root: Path, name: str) -> Path:
    directory = root
    for part in Path(name).parts:
        directory = directory / part
        directory.mkdir(exist_ok=True)
        write(directory, "README.md", f"# {part}\n\nWhat lives here.\n")
    return directory


def test_a_directory_that_documents_itself_is_indexed_by_its_relative_path(tmp_path):
    """Filing a tool where it belongs used to make it disappear; a README is what
    a later session reads anyway, so it is what earns the directory an index."""
    operations = document(tmp_path, "knowledge/operations")
    write(operations, "logging.md", "# Log structure\n\nRetention is 30 days.\n")
    ids = [as_command(s).id for s in scripts(tmp_path)]
    assert ids == [
        "knowledge/README.md",
        "knowledge/operations/README.md",
        "knowledge/operations/logging.md",
    ]
    assert scripts(tmp_path)[-1].run == "cat /shared/knowledge/operations/logging.md"


def test_an_extensionless_shebang_file_runs_as_itself(tmp_path):
    tools = document(tmp_path, "scripts")
    write(tools, "webshot", "#!/usr/bin/env -S uv run\n# Screenshot a URL.\n")
    (shot,) = [s for s in scripts(tmp_path) if s.path.name == "webshot"]
    assert shot.summary == "Screenshot a URL."
    assert shot.run == "/shared/scripts/webshot"


def test_a_vendored_tree_is_denied_however_well_documented(tmp_path):
    vendored = document(tmp_path, "node_modules")
    write(vendored, "index.js", "// a dependency\n")
    assert scripts(tmp_path) == []


def test_documentation_only_reaches_two_levels_down(tmp_path):
    deep = document(tmp_path, "a/b/c")
    write(deep, "buried.py", '"""Too far in to be capability."""\n')
    assert "a/b/c/buried.py" not in [s.path.as_posix() for s in scripts(tmp_path)]
    assert "a/b/README.md" in [s.path.as_posix() for s in scripts(tmp_path)]


def test_two_readmes_are_two_entries(tmp_path):
    document(tmp_path, "knowledge")
    document(tmp_path, "harness")
    commands = [as_command(s) for s in scripts(tmp_path)]
    assert len({c.id for c in commands}) == 2
    assert len({c.name for c in commands}) == 2


def test_the_root_survives_a_directory_with_more_files_than_the_cap(tmp_path):
    write(tmp_path, "main.py", '"""Project shared CLI."""\n')
    dumped = document(tmp_path, "zzz_notes")
    for index in range(80):
        write(dumped, f"note_{index:02d}.md", f"# Note {index}\n")
    found = scripts(tmp_path)
    assert found[0].path.as_posix() == "main.py"
    assert sum(1 for s in found if s.path.parent.name == "zzz_notes") == 40
