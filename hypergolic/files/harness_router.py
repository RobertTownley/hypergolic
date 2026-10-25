"""File-browsing endpoints scoped to ~/.hypergolic (no session required)."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from hypergolic.config.settings import HARNESS_DIR
from hypergolic.files.tree import build_file_tree, get_repo_root
from hypergolic.files.router import FileContentResponse, FileTreeResponse, read_file_response
from hypergolic.tools.file_walker import walk_files
from hypergolic.harness.app.state import get_app

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/harness/files", tags=["harness-files"])

_HARNESS_PROJECT_ID = "harness"


def _harness_root() -> Path:
    project = get_app().find_project(_HARNESS_PROJECT_ID)
    if project is not None:
        return Path(project.path)
    # Users may suppress the built-in harness project; the config viewer
    # should still browse ~/.hypergolic.
    if not HARNESS_DIR.is_dir():
        raise HTTPException(status_code=404, detail="Harness config directory not found")
    return HARNESS_DIR


@router.get("/tree", response_model=FileTreeResponse)
def get_harness_file_tree():
    root = _harness_root().resolve()
    return FileTreeResponse(
        session_id=_HARNESS_PROJECT_ID,
        root=get_repo_root(root),
        tree=build_file_tree(root),
    )


@router.get("/read", response_model=FileContentResponse)
def read_harness_file(path: str):
    return read_file_response(_harness_root().resolve(), path, _HARNESS_PROJECT_ID)


@router.get("/export")
def export_harness_config():
    """Stream a .zip of the harness config directory.

    Reuses ``walk_files`` so the archive honors the harness ``.gitignore``
    (dropping the session DB, logs, virtualenv, caches, eval reports, etc.)
    while keeping real config dotfiles like ``.gitignore`` itself. The config
    stores no secrets — every credential is read from environment variables at
    runtime — so files are archived verbatim.
    """
    root = _harness_root().resolve()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in walk_files(root, include_hidden=True):
            try:
                arcname = file_path.relative_to(root)
            except ValueError:
                continue
            archive.write(file_path, arcname=str(arcname))
    buffer.seek(0)

    filename = f"{root.name or 'hypergolic'}-config.zip"
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
