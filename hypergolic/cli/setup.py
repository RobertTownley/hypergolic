import subprocess
from pathlib import Path

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from rich.console import Console

console = Console()


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _find_ui_source_dir() -> Path | None:
    cwd = Path.cwd()
    candidates = [
        cwd / "ui",
        _package_root().parent / "ui",  # repo root / ui (flat layout)
    ]
    for candidate in candidates:
        if (candidate / "package.json").exists():
            return candidate
    return None


def build_ui() -> None:
    ui_dir = _find_ui_source_dir()
    if ui_dir is None:
        console.print(
            "[red]Error:[/] Cannot find ui/ directory with package.json. "
            "Run from the hypergolic repo root, or ensure the UI is pre-built.",
        )
        raise typer.Exit(1)

    console.print(f"Building UI from {ui_dir}...")
    result = subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=str(ui_dir))
    if result.returncode != 0:
        console.print("[red]Error:[/] pnpm install failed.")
        raise typer.Exit(1)

    result = subprocess.run(["pnpm", "run", "build"], cwd=str(ui_dir))
    if result.returncode != 0:
        console.print("[red]Error:[/] UI build failed.")
        raise typer.Exit(1)
    console.print("[green]UI build complete.[/]")


def run_migrations() -> None:
    root = _package_root()
    alembic_cfg = AlembicConfig(str(root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(root / "alembic"))
    alembic_cfg.attributes["configure_logger"] = False
    alembic_command.upgrade(alembic_cfg, "head")
