import re
import shutil
import subprocess
from pathlib import Path

from hypergolic.config.settings import HARNESS_DIR

import typer
from rich.console import Console

from hypergolic.cli.version import get_version
from hypergolic.dev_mode import is_dev_mode, source_root

console = Console()


def _package_contrib_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "contrib"


def _package_root() -> Path | None:
    return source_root()


def _default_shell_configs() -> list[Path]:
    return [
        Path.home() / ".zshrc",
        Path.home() / ".bashrc",
    ]


def _is_dev_mode() -> bool:
    if not is_dev_mode():
        return False
    if _package_root() is None:
        console.print(
            "[yellow]Warning:[/] HYPERGOLIC_DEV_MODE is set but no valid source checkout found. "
            "Falling back to non-dev mode."
        )
        return False
    return True


def init() -> None:
    """Initialize ~/.hypergolic/ with default configuration."""
    init_impl(
        root_dir=HARNESS_DIR,
        contrib_dir=_package_contrib_dir(),
        shell_configs=_default_shell_configs(),
    )


def init_impl(
    root_dir: Path,
    contrib_dir: Path,
    shell_configs: list[Path],
) -> None:
    """Core init logic, testable with injected paths."""
    if root_dir.exists():
        console.print(f"[yellow]Warning:[/] {root_dir} already exists.")
        overwrite = typer.confirm("Reinitialize? (your files won't be touched)")
        if not overwrite:
            raise typer.Exit()

    console.print(f"Initializing {root_dir}...")

    # Create directory structure
    root_dir.mkdir(parents=True, exist_ok=True)
    (root_dir / "prompts" / "roles").mkdir(parents=True, exist_ok=True)
    (root_dir / "prompts" / "skills").mkdir(parents=True, exist_ok=True)
    (root_dir / "projects").mkdir(parents=True, exist_ok=True)

    # Defaults are imported from the package at runtime via app.use_defaults();
    # they are no longer copied into the harness dir.
    main_py = root_dir / "main.py"
    if not main_py.exists():
        template = contrib_dir / "main_template.py"
        if template.exists():
            shutil.copy2(template, main_py)
            console.print(f"  Created {main_py}")
    else:
        console.print(f"  [dim]Skipping {main_py} (already exists)[/]")

    setup_gitignore(root_dir=root_dir, contrib_dir=contrib_dir)
    generate_pyproject(root_dir=root_dir)
    _run_uv_sync(root_dir=root_dir)
    _setup_shell_alias(root_dir=root_dir, shell_configs=shell_configs)
    _initial_git_commit(root_dir)

    console.print(f"\n[green]\u2713 Hypergolic initialized at {root_dir}[/]")
    console.print("\nNext steps:")
    console.print(f"  1. Edit {main_py} to configure your projects")
    console.print("  2. Restart your shell (or run: source ~/.zshrc)")
    console.print("  3. Run: h")


# Entries that must be present in the harness .gitignore.
# setup_gitignore() appends any that are missing.
_REQUIRED_GITIGNORE_ENTRIES = [
    "mcp_tokens/",
    "worktrees/",
]


def setup_gitignore(root_dir: Path | None = None, contrib_dir: Path | None = None) -> None:
    root = root_dir or HARNESS_DIR
    contrib = contrib_dir or _package_contrib_dir()
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        source = contrib / ".gitignore"
        if source.exists():
            shutil.copy2(source, gitignore)
        return
    # Ensure required entries are present in existing .gitignore
    content = gitignore.read_text()
    lines = {line.strip() for line in content.splitlines()}
    missing = [entry for entry in _REQUIRED_GITIGNORE_ENTRIES if entry not in lines]
    if missing:
        with open(gitignore, "a") as f:
            f.write("\n# Added by hypergolic update\n")
            for entry in missing:
                f.write(f"{entry}\n")


def generate_pyproject(root_dir: Path | None = None) -> None:
    root = root_dir or HARNESS_DIR
    pyproject = root / "pyproject.toml"
    version = get_version()

    if _is_dev_mode():
        pkg_root = _package_root()
        content = f'''[project]
name = "my-hypergolic"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "hypergolic",
]

[tool.uv]
package = false

[tool.uv.sources]
hypergolic = {{ path = "{pkg_root}", editable = true }}
'''
        pyproject.write_text(content)
        console.print(f"  {'Updated' if pyproject.exists() else 'Created'} {pyproject} (dev mode)")
    elif pyproject.exists():
        content = pyproject.read_text()
        content = re.sub(
            r'hypergolic[><=!~]+[\d.]+',
            f'hypergolic>={version}',
            content,
        )
        pyproject.write_text(content)
        console.print(f"  Updated {pyproject}")
    else:
        content = f'''[project]
name = "my-hypergolic"
version = "0.1.0"
requires-python = ">=3.14"
dependencies = [
    "hypergolic>={version}",
]

[tool.uv]
package = false
'''
        pyproject.write_text(content)
        console.print(f"  Created {pyproject}")


def _initial_git_commit(directory: Path) -> None:
    if not (directory / ".git").exists():
        subprocess.run(["git", "init"], cwd=directory, capture_output=True)

    subprocess.run(["git", "add", "-A"], cwd=directory, capture_output=True, check=True)

    result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=directory, capture_output=True)
    if result.returncode != 0:
        subprocess.run(
            ["git", "commit", "-m", "Initial harness configuration"],
            cwd=directory,
            capture_output=True,
            check=True,
        )
        console.print("  Created initial git commit")


def _run_uv_sync(root_dir: Path | None = None) -> None:
    root = root_dir or HARNESS_DIR
    console.print(f"  Running uv sync in {root}...")
    result = subprocess.run(["uv", "sync"], cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"  [yellow]Warning:[/] uv sync failed:\n{result.stderr}")
    else:
        console.print("  uv sync complete")


def _setup_shell_alias(
    root_dir: Path | None = None,
    shell_configs: list[Path] | None = None,
) -> None:
    root = root_dir or HARNESS_DIR
    alias_line = f"alias h='(cd {root} && uv run main.py)'"
    configs = shell_configs if shell_configs is not None else _default_shell_configs()

    for config_path in configs:
        if not config_path.exists():
            continue
        content = config_path.read_text()
        if "alias h=" in content:
            new_content = re.sub(r"alias h=.*", alias_line, content)
            if new_content == content:
                # Alias already up to date — nothing to write
                return
            confirmed = typer.confirm(
                f"Update existing shell alias in {config_path}?",
                default=True,
            )
            if confirmed:
                config_path.write_text(new_content)
                console.print(f"  Updated alias in {config_path}")
        else:
            confirmed = typer.confirm(
                f"Add shell alias to {config_path}?",
                default=True,
            )
            if confirmed:
                with open(config_path, "a") as f:
                    f.write(f"\n# Hypergolic\n{alias_line}\n")
                console.print(f"  Added alias to {config_path}")
        return

    console.print("  [yellow]Could not find shell config. Add this to your shell profile:[/]")
    console.print(f"    {alias_line}")
