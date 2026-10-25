import base64
import shlex
from collections.abc import Awaitable, Callable

from hypergolic.harness.primitives.results import ToolResult

LIMIT = 8_000
_HEAD = 6_000
_TAIL = 1_500
_CHUNK = 90_000
_MAX_SAVED = 4_000_000
OUT_DIR = "/tmp/hypergolic-out"

Run = Callable[[str], Awaitable[object]]


async def _save(run: Run, path: str, text: str) -> None:
    data = base64.b64encode(text[:_MAX_SAVED].encode()).decode()
    await run(f"mkdir -p {OUT_DIR} && : > {shlex.quote(path)}")
    for i in range(0, len(data), _CHUNK):
        chunk = data[i:i + _CHUNK]
        await run(f"printf %s {chunk} | base64 -d >> {shlex.quote(path)}")


def _cut(text: str, path: str) -> str:
    return (
        f"{text[:_HEAD]}\n[… {len(text) - _HEAD - _TAIL:,} chars cut; "
        f"full output: {path}]\n{text[-_TAIL:]}"
    )


async def spill_long_output(result: ToolResult, run: Run, name: str) -> ToolResult:
    first = result.content[0] if result.content else None
    if not isinstance(first, dict):
        return result
    text = first.get("text", "")
    if len(text) <= LIMIT:
        return result
    path = f"{OUT_DIR}/{name}.txt"
    try:
        await _save(run, path, text)
    except Exception:  # noqa: BLE001
        return result
    content = [{**first, "text": _cut(text, path)}, *result.content[1:]]
    return ToolResult(content=content, is_error=result.is_error, meta=result.meta)
