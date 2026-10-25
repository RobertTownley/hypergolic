from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import threading
from pathlib import Path
from types import ModuleType

from hypergolic.config.settings import HARNESS_DIR
from hypergolic.harness.app.core import App
from hypergolic.harness.app.onboarding import get_builtin_harness_project
from hypergolic.harness.app.state import live_app, set_app
from hypergolic.harness.app.validation import validate_app


class HarnessLoadError(RuntimeError):
    pass


_INSTALL_DIR_NAMES = frozenset({"site-packages", "dist-packages"})


def _in_dir(mod: object, root: Path) -> bool:
    file = getattr(mod, "__file__", None)
    if not file:
        return False
    path = Path(file)
    if not (str(path) + os.sep).startswith(str(root).rstrip(os.sep) + os.sep):
        return False
    if _INSTALL_DIR_NAMES.intersection(path.relative_to(root).parts):
        return False
    return not any(
        path.is_relative_to(prefix)
        for prefix in {Path(sys.prefix), Path(sys.base_prefix)}
        if prefix.is_relative_to(root)
    )


def evict_harness_modules(root: Path) -> dict[str, ModuleType]:
    evicted = {name: mod for name, mod in sys.modules.items() if _in_dir(mod, root)}
    for name in evicted:
        del sys.modules[name]
    importlib.invalidate_caches()
    return evicted


def load_harness_app(harness_dir: Path = HARNESS_DIR) -> App:
    previous = live_app()
    try:
        return _exec_main(harness_dir)
    finally:
        if previous is not None:
            set_app(previous)


def _exec_main(harness_dir: Path) -> App:
    main_py = harness_dir / "main.py"
    if not main_py.exists():
        raise HarnessLoadError(
            f"No harness found at {main_py}; run `hypergolic init` first"
        )
    sys.path.insert(0, str(harness_dir))
    spec = importlib.util.spec_from_file_location("_hypergolic_harness_main", main_py)
    if spec is None or spec.loader is None:
        raise HarnessLoadError(f"Cannot build an import spec for {main_py}")
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise HarnessLoadError(f"Failed to import {main_py}: {exc}") from exc

    apps = [v for v in vars(module).values() if isinstance(v, App)]
    if not apps:
        raise HarnessLoadError(f"{main_py} defines no App instance")
    return apps[0]


def finalize_app(app: App) -> None:
    if not app.find_project("harness"):
        app.register_project(get_builtin_harness_project())
    errors = validate_app(app)
    if errors:
        raise HarnessLoadError(
            "Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors)
        )
    app._expand_paths()


def prepare_app(app: App) -> None:
    set_app(app)
    finalize_app(app)


_reload_lock = threading.Lock()


def reload_live_harness(harness_dir: Path = HARNESS_DIR) -> App:
    with _reload_lock:
        saved_path = list(sys.path)
        evicted = evict_harness_modules(harness_dir)
        try:
            app = load_harness_app(harness_dir)
            finalize_app(app)
        except Exception:
            evict_harness_modules(harness_dir)
            sys.modules.update(evicted)
            raise
        finally:
            sys.path[:] = saved_path
        set_app(app)
        return app
