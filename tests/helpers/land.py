from typing import Any

import pytest

from hypergolic.contrib.tools import land
from hypergolic.contrib.tools.land import dest, pipeline, target

LAND_MODULES = (land, pipeline, dest, target)


def patch_land(monkeypatch: pytest.MonkeyPatch, patches: dict[str, Any]) -> None:
    for name, value in patches.items():
        owners = [m for m in LAND_MODULES if hasattr(m, name)]
        assert owners, f"no land module has {name}"
        for module in owners:
            monkeypatch.setattr(module, name, value)
