from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from hypergolic.harness.app.core import App


def expand_paths(app: App) -> None:
    for p in app.projects:
        p.git_root = str(Path(p.git_root).expanduser())
        if p.prompt_path:
            p.prompt_path = str(Path(p.prompt_path).expanduser())


def run_app(app: App) -> None:
    from rich.console import Console

    import hypergolic.config.settings as settings
    from hypergolic.cli.init_cmd import setup_gitignore
    from hypergolic.cli.setup import build_ui
    from hypergolic.dev_mode import is_dev_mode
    from hypergolic.harness.app.launcher import launch
    from hypergolic.harness.app.onboarding import get_builtin_harness_project
    from hypergolic.harness.app.safe_mode import enter_safe_mode
    from hypergolic.harness.app.state import set_app
    from hypergolic.harness.app.validation import validate_app
    from hypergolic.logging import setup_logging

    console = Console()
    safe = "--safe" in sys.argv

    setup_logging()

    set_app(app)

    if is_dev_mode():
        console.print("[dim]Dev mode: rebuilding frontend...[/]")
        build_ui()
        setup_gitignore()

    if safe:
        enter_safe_mode(app)
        launch(app, safe=True)
        return

    harness_dir = settings.HARNESS_DIR
    if not (harness_dir / ".git").exists():
        subprocess.run(["git", "init"], cwd=harness_dir, capture_output=True)

    if not app.find_project("harness"):
        app.register_project(get_builtin_harness_project())

    errors = validate_app(app)
    if errors:
        console.print("\n[red]Configuration errors:[/]")
        for err in errors:
            console.print(f"  [red]\u2022[/] {err}")
        try:
            answer = (
                input(
                    "\nLaunch in safe mode? (contrib tools only, no user config) [Y/n] "
                )
                .strip()
                .lower()
            )
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("n", "no"):
            console.print("\n[red]Fix the errors in your main.py and try again.[/]")
            return
        enter_safe_mode(app)
        launch(app, safe=True)
        return

    launch(app, safe=False)
