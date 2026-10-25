import ast
import asyncio
import shutil
import sys
from pathlib import Path

from hypergolic.harness.primitives.results import ToolResult
from hypergolic.harness.primitives.tool import Tool, ToolContext
from hypergolic.git.harness_repo import harness_workspace_path


def _harness_root(session_id: str) -> Path:
    """The session's /harness workspace — validation has to see the edits the
    agent just made, not last merge's state."""
    return harness_workspace_path(session_id)


def _check_filesystem(root: Path) -> tuple[list[str], int]:
    """Check harness filesystem health. Returns (issues, checks_passed)."""
    issues: list[str] = []
    checks_passed = 0

    main_py = root / "main.py"
    if not main_py.exists():
        issues.append(f"main.py not found at {main_py}")
    else:
        checks_passed += 1
        try:
            ast.parse(main_py.read_text())
            checks_passed += 1
        except SyntaxError as e:
            issues.append(f"main.py syntax error: {e}")

    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        issues.append("pyproject.toml not found")
    else:
        checks_passed += 1

    return issues, checks_passed


async def _run_subprocess(
    args: list[str], cwd: str, timeout: int, error_label: str, use_stdout: bool = False
) -> tuple[list[str], int]:
    issues: list[str] = []
    checks_passed = 0
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode != 0:
            output = (stdout_bytes if use_stdout else stderr_bytes).decode(errors="replace").strip()
            lines = output.splitlines()
            if len(lines) > 20:
                output = "\n".join(lines[-20:])
            issues.append(f"{error_label}:\n{output}")
        else:
            checks_passed += 1
    except TimeoutError:
        issues.append(f"{error_label} timed out (>{timeout}s)")
    except Exception as e:
        issues.append(f"{error_label} error: {e}")
    return issues, checks_passed


def _build_validate_snippet(root: Path) -> str:
    return f"""
import sys
sys.path.insert(0, {str(root)!r})
import main
from hypergolic.harness.app.state import get_app
from hypergolic.harness.app.validation import validate_app
try:
    app = get_app()
except RuntimeError:
    print("ERROR: main.py did not call set_app()", file=sys.stderr)
    sys.exit(1)
errors = validate_app(app)
if errors:
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1)
"""


async def _check_import_and_config(root: Path) -> tuple[list[str], int]:
    """Import main.py and validate_app() in a subprocess against the current harness files."""
    return await _run_subprocess(
        args=[sys.executable, "-c", _build_validate_snippet(root)],
        cwd=str(root),
        timeout=20,
        error_label="main.py import/config failed",
    )


async def _check_types(root: Path) -> tuple[list[str], int]:
    """Run ty check over the harness directory."""
    if not shutil.which("ty"):
        return [], 0  # ty not installed; skip silently
    return await _run_subprocess(
        args=["ty", "check", str(root)],
        cwd=str(root),
        timeout=30,
        error_label="Type errors",
        use_stdout=True,
    )


async def run_validate_harness(ctx: ToolContext) -> ToolResult:
    issues: list[str] = []
    checks_passed = 0

    root = _harness_root(ctx.session.id)
    fs_issues, fs_passed = _check_filesystem(root)
    issues.extend(fs_issues)
    checks_passed += fs_passed

    has_valid_syntax = (root / "main.py").exists() and not any(
        "main.py" in i for i in issues
    )
    if has_valid_syntax:
        import_issues, import_passed = await _check_import_and_config(root)
        issues.extend(import_issues)
        checks_passed += import_passed

        type_issues, type_passed = await _check_types(root)
        issues.extend(type_issues)
        checks_passed += type_passed

    if issues:
        text = f"{len(issues)} issue(s) found:\n" + "\n".join(
            f"  \u2022 {i}" for i in issues
        )
        text += f"\n\n{checks_passed} check(s) passed"
        return ToolResult.text(text, is_error=True)

    return ToolResult.text(f"All {checks_passed} checks passed. Harness is healthy.")


validate_harness_tool = Tool(
    id="validate_harness",
    tags=["validate", "lint", "typecheck", "config-check", "harness-health", "broken-config"],
    name="Validate Harness",
    description="Validate the harness config (your /harness edits): integrity + ty type checks",
    run=run_validate_harness,
)
