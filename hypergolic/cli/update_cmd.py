from hypergolic.config.settings import HARNESS_DIR

import typer
from rich.console import Console

from hypergolic.cli.init_cmd import _run_uv_sync, generate_pyproject, setup_gitignore
from hypergolic.git.harness_repo import ensure_harness_repo
from hypergolic.cli.version import get_version

console = Console()


def update() -> None:
    """Update the harness's pinned hypergolic version and dependencies.

    Defaults (tools/roles/skills/prompts) ship with the package and are loaded
    via ``app.use_defaults()``, so there is nothing to copy — updating is just
    bumping the version pin and re-syncing the environment.
    """
    if not HARNESS_DIR.exists():
        console.print(f"[red]Error:[/] {HARNESS_DIR} does not exist. Run `hypergolic init` first.")
        raise typer.Exit(1)

    version = get_version()
    console.print(f"Updating harness to hypergolic {version}...")

    generate_pyproject()
    setup_gitignore()
    ensure_harness_repo()
    _run_uv_sync()

    console.print(f"\n[green]✓ Harness updated to {version}[/]")
