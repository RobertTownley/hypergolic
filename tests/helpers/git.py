from __future__ import annotations

import atexit
import shutil
import subprocess
import tempfile
from pathlib import Path

class FakeGit:
    def __init__(self, responses: dict[tuple[str, ...], str] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, ...]] = []

    async def __call__(self, cwd: Path, *args: str, **_: object) -> str:
        self.calls.append(args)
        matches = [p for p in self.responses if args[:len(p)] == p]
        return self.responses[max(matches, key=len)] if matches else ""

    async def run(self, *args: str, cwd: Path | None = None, **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(["git", *args], 0, await self(cwd or Path(), *args), "")


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True,
    )


_template: Path | None = None


def init_repo(path: Path) -> None:
    global _template
    if path.exists() and any(path.iterdir()):
        _init_in_place(path)
        return
    if _template is None:
        _template = Path(tempfile.mkdtemp(prefix="hg-git-template-")) / "repo"
        _init_in_place(_template)
        atexit.register(shutil.rmtree, _template.parent, True)
    shutil.copytree(_template, path, symlinks=True, dirs_exist_ok=True)


def _init_in_place(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(path)], check=True, capture_output=True)
    run_git(path, "config", "user.email", "t@t")
    run_git(path, "config", "user.name", "t")
    (path / "README.md").write_text("readme\n")
    run_git(path, "add", "-A")
    run_git(path, "commit", "-m", "init")


def copy_repo(src: Path, dst: Path) -> Path:
    shutil.copytree(src, dst, symlinks=True)
    return dst


def clone_workspace(repo: Path, ws: Path, branch: str) -> None:
    subprocess.run(
        ["git", "clone", "--quiet", "--shared", "-c", "user.email=t@t", "-c", "user.name=t",
         str(repo), str(ws)],
        check=True, capture_output=True,
    )
    run_git(ws, "checkout", "--quiet", "-b", branch)


def commit_file(repo: Path, name: str, content: str, message: str = "feat") -> None:
    (repo / name).write_text(content)
    run_git(repo, "add", name)
    run_git(repo, "commit", "-m", message)


def seed_worktree_session(
    tmp_path, *, pid: str = "wt-proj", path: str | None = None,
) -> tuple[str, Path]:
    from tests.conftest import make_project, make_session

    make_project(pid=pid, name="Test", path=path or str(tmp_path / "base"))
    wt = tmp_path / "wt"
    wt.mkdir()
    make_session(sid="wt-sess", project_id=pid, worktree_path=str(wt), worktree_branch="feat")
    return "wt-sess", wt


def sync_merge(repo: Path, *, conflict: bool = False) -> tuple[str, str]:
    run_git(repo, "checkout", "-q", "-b", "pr")
    commit_file(repo, "f.txt", "pr side\n" if conflict else "pr\n", "pr work")
    pr_tip = run_git(repo, "rev-parse", "HEAD").stdout.strip()
    run_git(repo, "checkout", "-q", "main")
    commit_file(repo, "m1.txt", "m1\n", "main one")
    commit_file(repo, "f.txt" if conflict else "m2.txt", "main side\n", "main two")
    run_git(repo, "checkout", "-q", "pr")
    if conflict:
        subprocess.run(["git", "-C", str(repo), "merge", "main"], capture_output=True)
        (repo / "f.txt").write_text("resolved\n")
        run_git(repo, "add", "f.txt")
        run_git(repo, "-c", "core.editor=true", "commit", "-q", "-m", "Merge main into pr")
    else:
        run_git(repo, "merge", "-q", "--no-edit", "main")
    return pr_tip, run_git(repo, "rev-parse", "HEAD").stdout.strip()
