import pytest

from hypergolic.telemetry.exec_metrics import program_of


@pytest.mark.parametrize(("command", "expected"), [
    ("git status", "git"),
    ("cd /app && uv run pytest -x hypergolic", "pytest"),
    ("FOO=1 timeout 30 /usr/bin/python -c 'x'", "python"),
    ("cd /app; npx vitest run", "vitest"),
    ("cd /app", "other"),
    ("echo 'unterminated", "echo"),
    ("set -e\ngit fetch origin", "git"),
    ("cd /tmp; export TOKEN=x; uv run /shared/main.py ui shot /", "main.py"),
    ("set -euo pipefail", "other"),
])
def test_program_of(command: str, expected: str) -> None:
    assert program_of(command) == expected
