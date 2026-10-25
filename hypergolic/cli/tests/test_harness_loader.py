import sys
from pathlib import Path

import pytest

from hypergolic.cli.harness_loader import (
    HarnessLoadError,
    load_harness_app,
    reload_live_harness,
)
from hypergolic.harness.app.core import App
from hypergolic.harness.app.state import get_app, set_app


def test_missing_main_py(tmp_path: Path):
    with pytest.raises(HarnessLoadError, match="hypergolic init"):
        load_harness_app(tmp_path)


def test_import_error_surfaces(tmp_path: Path):
    (tmp_path / "main.py").write_text("import definitely_not_a_module\n")
    with pytest.raises(HarnessLoadError, match="Failed to import"):
        load_harness_app(tmp_path)


def test_no_app_instance(tmp_path: Path):
    (tmp_path / "main.py").write_text("x = 1\n")
    with pytest.raises(HarnessLoadError, match="no App instance"):
        load_harness_app(tmp_path)


def test_loads_app_without_running_it(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "from hypergolic.harness.app.core import App\n"
        "app = App(truncate_token_threshold=123)\n"
        "ran = []\n"
        "if __name__ == '__main__':\n"
        "    ran.append(True)  # must not execute on load\n"
        "    app()\n"
    )
    app = load_harness_app(tmp_path)
    assert app.truncate_token_threshold == 123


def test_harness_dir_on_sys_path(tmp_path: Path):
    (tmp_path / "sibling.py").write_text("VALUE = 42\n")
    (tmp_path / "main.py").write_text(
        "import sibling\n"
        "from hypergolic.harness.app.core import App\n"
        "app = App()\n"
        "assert sibling.VALUE == 42\n"
    )
    assert load_harness_app(tmp_path) is not None


# ── live-App safety and in-place reload ──────────────────────────────────────


def _write_main(root: Path, marker: str) -> None:
    (root / "extras.py").write_text(f'MARKER = "{marker}"\n')
    (root / "main.py").write_text(
        "from hypergolic.harness.app.core import App\n"
        "from hypergolic.harness.app.state import set_app\n"
        "import extras\n"
        "app = App()\n"
        "app.use_defaults()\n"
        "app.marker = extras.MARKER\n"
        "set_app(app)\n"
    )


def test_load_does_not_replace_the_live_app_when_main_calls_set_app(tmp_path: Path):
    live = App()
    set_app(live)
    _write_main(tmp_path, "loaded")
    loaded = load_harness_app(tmp_path)
    assert getattr(loaded, "marker") == "loaded"
    assert get_app() is live
    sys.modules.pop("extras", None)


def test_reload_picks_up_edits_and_swaps_the_live_app(tmp_path: Path):
    # Markers differ in length: .pyc validity is (mtime seconds, size), so a
    # same-size edit within one second would reuse stale bytecode.
    _write_main(tmp_path, "v1")
    first = reload_live_harness(tmp_path)
    assert get_app() is first and getattr(first, "marker") == "v1"

    _write_main(tmp_path, "v2-edited")
    second = reload_live_harness(tmp_path)
    assert get_app() is second and getattr(second, "marker") == "v2-edited"
    assert second is not first
    sys.modules.pop("extras", None)


def test_reload_failure_keeps_previous_app_and_modules(tmp_path: Path):
    _write_main(tmp_path, "v1")
    first = reload_live_harness(tmp_path)
    extras_v1 = sys.modules["extras"]
    path_before = list(sys.path)

    (tmp_path / "extras.py").write_text("raise RuntimeError('broken edit')  # longer than v1\n")
    with pytest.raises(HarnessLoadError, match="broken edit"):
        reload_live_harness(tmp_path)

    assert get_app() is first
    assert sys.modules["extras"] is extras_v1
    assert sys.path == path_before
    sys.modules.pop("extras", None)


# ── eviction scope ───────────────────────────────────────────────────────────


def _fake_module(name: str, file: Path):
    from types import ModuleType

    mod = ModuleType(name)
    mod.__file__ = str(file)
    return mod


def test_evict_keeps_installed_packages_under_the_harness_dir(tmp_path: Path, monkeypatch):
    from hypergolic.cli.harness_loader import evict_harness_modules

    site = tmp_path / ".venv" / "lib" / "python3.13" / "site-packages"
    harness_mod = _fake_module("hg_test_harness_mod", tmp_path / "projects" / "x.py")
    lib_mod = _fake_module("hg_test_lib_mod", site / "lib_mod" / "__init__.py")
    for mod in (harness_mod, lib_mod):
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

    evicted = evict_harness_modules(tmp_path)

    assert "hg_test_harness_mod" in evicted
    assert "hg_test_lib_mod" not in evicted
    assert sys.modules["hg_test_lib_mod"] is lib_mod


def test_evict_keeps_the_running_environment_under_the_harness_dir(tmp_path: Path, monkeypatch):
    from hypergolic.cli.harness_loader import evict_harness_modules

    venv = tmp_path / ".venv"
    monkeypatch.setattr(sys, "prefix", str(venv))
    env_mod = _fake_module("hg_test_env_mod", venv / "lib" / "python3.13" / "env_mod.py")
    monkeypatch.setitem(sys.modules, env_mod.__name__, env_mod)

    assert "hg_test_env_mod" not in evict_harness_modules(tmp_path)
    assert sys.modules["hg_test_env_mod"] is env_mod
