from importlib.metadata import version as pkg_version


def get_version() -> str:
    try:
        return pkg_version("hypergolic")
    except Exception:
        return "unknown"
