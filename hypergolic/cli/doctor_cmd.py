import ast

import typer
from rich.console import Console
from hypergolic.config.settings import HARNESS_DIR
from hypergolic.git.worktree_doctor import reconcile_worktrees
from hypergolic.config.settings import settings
from hypergolic.db import container as db_container
from hypergolic.system.docker import ContainerError

console = Console()


def doctor() -> None:
    """Validate Hypergolic setup: files, deps, paths, database."""
    issues: list[str] = []
    warnings: list[str] = []
    checks_passed = 0

    main_py = HARNESS_DIR / "main.py"
    if not main_py.exists():
        issues.append(f"main.py not found at {main_py}")
    else:
        checks_passed += 1
        try:
            ast.parse(main_py.read_text())
            checks_passed += 1
        except SyntaxError as e:
            issues.append(f"main.py has syntax error: {e}")

    pyproject = HARNESS_DIR / "pyproject.toml"
    if not pyproject.exists():
        issues.append(f"pyproject.toml not found at {pyproject}")
    else:
        checks_passed += 1


    if not db_container.docker_running():
        issues.append("Docker is not running (sessions and the database need it)")
    else:
        checks_passed += 1
        if "HYPERGOLIC_DATABASE_URL" in settings.model_fields_set:
            # Externally-managed Postgres; reachability is reported when the
            # app connects.
            checks_passed += 1
        else:
            try:
                db_container.ensure_postgres()
                checks_passed += 1
            except ContainerError as exc:
                issues.append(str(exc))

    try:
        report = reconcile_worktrees()
        if report.is_clean():
            checks_passed += 1
        else:
            if report.orphan_dirs_removed:
                warnings.append(
                    f"Removed {len(report.orphan_dirs_removed)} orphan worktree director(y/ies)"
                )
            if report.stale_rows_cleared:
                warnings.append(
                    f"Cleared worktree_path on {len(report.stale_rows_cleared)} session row(s)"
                )
            if report.orphan_volumes_removed:
                warnings.append(
                    f"Removed {len(report.orphan_volumes_removed)} orphan gitdir volume(s)"
                )
            if report.orphan_internals_removed:
                warnings.append(
                    f"Removed {len(report.orphan_internals_removed)} orphan session internals dir(s)"
                )
    except Exception as e:  # pragma: no cover - defensive
        warnings.append(f"Worktree reconciliation failed: {e}")

    console.print()
    if issues:
        console.print(f"[red]\u2717 {len(issues)} issue(s) found:[/]")
        for issue in issues:
            console.print(f"  [red]\u2022[/] {issue}")
    if warnings:
        console.print(f"[yellow]\u26a0 {len(warnings)} warning(s):[/]")
        for warning in warnings:
            console.print(f"  [yellow]\u2022[/] {warning}")

    console.print(f"\n[green]\u2713 {checks_passed} check(s) passed[/]")

    if issues:
        raise typer.Exit(1)
