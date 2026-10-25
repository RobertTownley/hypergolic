from pathlib import Path

from hypergolic.schemas import Session


def resolve_path(path: str, session: Session) -> Path:
    """Resolve a user-supplied path to an absolute, symlink-resolved Path.

    Handles three forms:
    - Absolute paths: ``/foo/bar`` → resolved as-is
    - Home-relative paths: ``~/foo`` → expanded then resolved
    - Relative paths: ``src/main.py`` → resolved against ``session.working_directory()``
    """
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = session.working_directory() / p
    return p.resolve()

