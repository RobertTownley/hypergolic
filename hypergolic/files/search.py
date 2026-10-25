"""File name and content search."""

import subprocess
from pathlib import Path

from hypergolic.files.schemas import FileSearchMatch
from hypergolic.tools.file_walker import walk_files
from hypergolic.tools.subprocess_util import has_ripgrep


def search_file_names(
    query: str, repo_root: Path, respect_gitignore: bool, include_hidden: bool, max_results: int,
) -> list[FileSearchMatch]:
    """Search for files whose path matches all parts of *query*."""
    cmd = ["git", "ls-files", "--cached", "--others"]
    if respect_gitignore:
        cmd.append("--exclude-standard")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, cwd=repo_root, timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return []

    query_parts = query.lower().split()
    matches: list[FileSearchMatch] = []

    for line in result.stdout.splitlines():
        path = line.strip()
        if not path:
            continue
        if not include_hidden and any(part.startswith(".") for part in Path(path).parts):
            continue
        path_lower = path.lower()
        if all(part in path_lower for part in query_parts):
            matches.append(FileSearchMatch(path=path))
            if len(matches) >= max_results:
                break

    def sort_key(m: FileSearchMatch) -> tuple[int, int, str]:
        name = Path(m.path).name.lower()
        basename_match = 0 if all(p in name for p in query_parts) else 1
        return (basename_match, len(m.path), m.path.lower())

    matches.sort(key=sort_key)
    return matches[:max_results]


def _parse_search_output(
    stdout: str, repo_root: Path, max_results: int,
) -> list[FileSearchMatch]:
    matches: list[FileSearchMatch] = []
    for line in stdout.splitlines():
        if not line or line == "--":
            continue
        try:
            path_rest = line.split(":", 2)
            if len(path_rest) < 3:
                continue
            raw_path, line_no_str, text = path_rest
            try:
                rel_path = str(Path(raw_path).relative_to(repo_root))
            except ValueError:
                rel_path = raw_path
            matches.append(FileSearchMatch(
                path=rel_path, line=int(line_no_str), text=text.strip()[:200],
            ))
        except (ValueError, TypeError):
            continue
        if len(matches) >= max_results:
            break
    return matches


def _search_contents_rg(
    query: str, repo_root: Path, respect_gitignore: bool, include_hidden: bool, max_results: int,
) -> list[FileSearchMatch]:
    cmd = [
        "rg", "--line-number", "--color=never", "--no-heading",
        "--max-count", "3", "--fixed-strings", "--ignore-case",
    ]
    if not respect_gitignore:
        cmd.append("--no-ignore")
    if include_hidden:
        cmd.append("--hidden")
    cmd.extend([query, str(repo_root)])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, cwd=repo_root,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode > 1:
        return []

    return _parse_search_output(result.stdout, repo_root, max_results)


def _search_contents_python(
    query: str, repo_root: Path, respect_gitignore: bool, include_hidden: bool, max_results: int,
) -> list[FileSearchMatch]:
    needle = query.lower()
    matches: list[FileSearchMatch] = []
    for path in walk_files(repo_root, include_hidden=include_hidden):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\x00" in data[:8192]:
            continue
        rel = str(path.relative_to(repo_root))
        hits = [
            FileSearchMatch(path=rel, line=i, text=line.strip()[:200])
            for i, line in enumerate(data.decode(errors="replace").splitlines(), 1)
            if needle in line.lower()
        ][:3]
        matches.extend(hits)
        if len(matches) >= max_results:
            return matches[:max_results]
    return matches


def search_file_contents(
    query: str, repo_root: Path, respect_gitignore: bool, include_hidden: bool, max_results: int,
) -> list[FileSearchMatch]:
    """Search file contents using ripgrep (if available) or pure-Python fallback."""
    if has_ripgrep():
        return _search_contents_rg(query, repo_root, respect_gitignore, include_hidden, max_results)
    return _search_contents_python(query, repo_root, respect_gitignore, include_hidden, max_results)
