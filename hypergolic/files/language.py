"""Filename-to-language mapping for syntax highlighting in the UI."""

from __future__ import annotations

from pathlib import Path

EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".json": "json",
    ".css": "css",
    ".html": "html",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".sh": "bash",
    ".bash": "bash",
    ".rs": "rust",
    ".go": "go",
    ".sql": "sql",
    ".xml": "xml",
    ".ini": "ini",
    ".cfg": "ini",
    ".dockerfile": "docker",
    ".makefile": "makefile",
}


def detect_language(path: str) -> str:
    p = Path(path)
    if p.name == "Dockerfile":
        return "docker"
    if p.name == "Makefile":
        return "makefile"
    return EXT_TO_LANGUAGE.get(p.suffix.lower(), "text")
