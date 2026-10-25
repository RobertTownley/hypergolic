"""Attach in-sandbox image files to a `cmd` tool result.

A command that wants the model to *see* an image prints a sentinel line:

    HYPERGOLIC_IMAGE:/absolute/path.png

The host fetches each file over a quiet follow-up exec (no output streaming —
base64 must never flood the UI), re-encodes it within provider limits, and
appends real image blocks to the tool result.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import PurePosixPath

from hypergolic.attachments.processing import process_image

logger = logging.getLogger(__name__)

SENTINEL = "HYPERGOLIC_IMAGE:"
MAX_IMAGES = 4

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

FetchFile = Callable[[str], Awaitable[bytes]]


async def extract_image_blocks(stdout: str, fetch: FetchFile) -> tuple[str, list[dict]]:
    """Replace sentinel lines in *stdout* with notes; return image blocks.

    Failures degrade to an inline note rather than failing the exec: the
    command's real output is still the primary result.
    """
    if SENTINEL not in stdout:
        return stdout, []

    blocks: list[dict] = []
    out_lines: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped.startswith(SENTINEL):
            out_lines.append(line)
            continue
        path = stripped[len(SENTINEL):].strip()
        note = await _attach(path, blocks, fetch)
        out_lines.append(note)
    tail = "\n" if stdout.endswith("\n") else ""
    return "\n".join(out_lines) + tail, blocks


async def _attach(path: str, blocks: list[dict], fetch: FetchFile) -> str:
    if len(blocks) >= MAX_IMAGES:
        return f"[image {path}: skipped, max {MAX_IMAGES} images per command]"
    media_type = _MEDIA_TYPES.get(PurePosixPath(path).suffix.lower())
    if media_type is None:
        return f"[image {path}: unsupported extension]"
    try:
        data = await fetch(path)
        encoded, media_type = process_image(data, media_type)
    except Exception as e:  # noqa: BLE001
        logger.warning("Image attach failed for %s", path, exc_info=True)
        return f"[image {path}: {e}]"
    blocks.append({
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": encoded},
    })
    return f"[image attached: {path}]"
