import copy
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from hypergolic.config.settings import HARNESS_DIR
from hypergolic.telemetry.log_context import ContextFilter

from uvicorn.config import LOGGING_CONFIG

ERROR_LOG_PATH = HARNESS_DIR / "errors.log"
SERVER_LOG_PATH = HARNESS_DIR / "server.log"
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s:%(hg_context)s %(message)s"

_initialized = False
_server_handler = None


def _rotating_handler(path: Path, level: int) -> RotatingFileHandler:
    handler = RotatingFileHandler(path, maxBytes=MAX_LOG_BYTES, backupCount=BACKUP_COUNT)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler.addFilter(ContextFilter())
    return handler


def setup_logging() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    HARNESS_DIR.mkdir(parents=True, exist_ok=True)

    logging.getLogger("hypergolic").setLevel(logging.DEBUG)
    logging.getLogger("hypergolic").addHandler(
        _rotating_handler(ERROR_LOG_PATH, logging.WARNING)
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(get_server_handler())
    # Root now has a handler, so lastResort no longer prints warnings to the
    # terminal; restore that explicitly.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter(_FORMAT))
    stderr_handler.addFilter(ContextFilter())
    root.addHandler(stderr_handler)


def get_server_handler() -> RotatingFileHandler:
    global _server_handler
    if _server_handler is None:
        HARNESS_DIR.mkdir(parents=True, exist_ok=True)
        _server_handler = _rotating_handler(SERVER_LOG_PATH, logging.INFO)
    return _server_handler


def uvicorn_log_config() -> dict:
    """Uvicorn applies its config via non-incremental dictConfig at startup,
    wiping any handlers attached earlier; inject ours into the config instead.
    The ``()`` factory reuses the singleton handler so root and uvicorn share
    one rotator."""
    cfg = copy.deepcopy(LOGGING_CONFIG)
    cfg["handlers"]["server_file"] = {"()": "hypergolic.logging.get_server_handler"}
    for name in ("uvicorn", "uvicorn.access"):
        cfg["loggers"][name]["handlers"].append("server_file")
    return cfg
