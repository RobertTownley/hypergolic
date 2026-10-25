"""Guard the import cost: small modules must not pull in the whole app.

Each case imports a module in a fresh interpreter and checks that heavy
packages are absent from ``sys.modules``. One new top-level import can bring
the full cost back, and nothing else would notice.
"""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.timeout(15)

HEAVY = ("anthropic", "sqlalchemy", "fastapi", "mcp", "opentelemetry", "hypergolic.harness.app.core")

LIBRARIES = ("anthropic", "sqlalchemy", "fastapi", "mcp")

CASES = [
    ("hypergolic", HEAVY),
    ("hypergolic.enums", HEAVY),
    ("hypergolic.harness.primitives.tool", LIBRARIES),
    ("hypergolic.contrib.tools.activate_skill", LIBRARIES),
    ("hypergolic.contrib.tools.dispatch", LIBRARIES),
    ("hypergolic.contrib.tools.history", LIBRARIES),
    ("hypergolic.contrib.tools.mcp_command", LIBRARIES),
    ("hypergolic.contrib.tools.pull_request", LIBRARIES),
    ("hypergolic.contrib.tools.readiness", LIBRARIES),
    ("hypergolic.contrib.tools.review", LIBRARIES),
    ("hypergolic.telemetry.sandbox_metrics", LIBRARIES),
    ("hypergolic.workflows.resolver", LIBRARIES),
]


@pytest.mark.parametrize(("module", "forbidden"), CASES)
def test_import_does_not_load_heavy_packages(module, forbidden):
    probe = (
        f"import sys, {module}\n"
        f"loaded = [m for m in {forbidden!r} if m in sys.modules]\n"
        "print(','.join(loaded))\n"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "", f"import {module} loaded: {out.stdout.strip()}"


def test_public_api_resolves_on_access():
    import hypergolic

    assert hypergolic.App.__name__ == "App"
    assert sorted(hypergolic._EXPORTS) == hypergolic.__all__
    assert set(hypergolic.__all__) <= set(dir(hypergolic))
    with pytest.raises(AttributeError):
        _ = hypergolic.NotAName
