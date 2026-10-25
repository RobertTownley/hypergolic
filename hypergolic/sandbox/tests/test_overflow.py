from hypergolic.harness.primitives.results import ToolResult
from hypergolic.sandbox.tool.overflow import LIMIT, spill_long_output


async def test_short_output_untouched():
    result = ToolResult.text("ok")
    assert await spill_long_output(result, _never, "id") is result


async def test_long_output_is_saved_and_cut():
    cmds: list[str] = []

    async def run(cmd: str) -> None:
        cmds.append(cmd)

    text = "a" * LIMIT + "TAIL"
    out = await spill_long_output(ToolResult.text(text), run, "tu1")
    shown = out.content[0]["text"]
    assert "full output: /tmp/hypergolic-out/tu1.txt" in shown
    assert shown.endswith("TAIL") and len(shown) < LIMIT
    assert any("base64 -d >> /tmp/hypergolic-out/tu1.txt" in c for c in cmds)


async def test_save_failure_keeps_full_output():
    async def boom(cmd: str) -> None:
        raise RuntimeError

    result = ToolResult.text("x" * (LIMIT + 1))
    assert await spill_long_output(result, boom, "id") is result


async def _never(cmd: str) -> None:
    raise AssertionError
