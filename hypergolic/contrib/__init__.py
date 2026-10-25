from pathlib import Path

_CONTRIB_DIR = Path(__file__).resolve().parent


def contrib_path(*parts: str) -> str:
    """Absolute path to a file shipped under ``hypergolic/contrib/``.

    Default prompts, the sandbox config, etc. are read straight from the
    installed package — they are no longer copied into ``~/.hypergolic``.
    """
    return str(_CONTRIB_DIR.joinpath(*parts))
