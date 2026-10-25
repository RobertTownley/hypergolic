import base64
import io

from PIL import Image

from hypergolic.sandbox.tool.images import MAX_IMAGES, extract_image_blocks


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


async def test_no_sentinel_passthrough():
    out, blocks = await extract_image_blocks("plain output\n", _fail_fetch)
    assert out == "plain output\n"
    assert blocks == []


async def _fail_fetch(path: str) -> bytes:
    raise AssertionError("must not fetch")


async def test_sentinel_becomes_image_block():
    png = _png_bytes()

    async def fetch(path: str) -> bytes:
        assert path == "/tmp/shot.png"
        return png

    out, blocks = await extract_image_blocks(
        "before\nHYPERGOLIC_IMAGE:/tmp/shot.png\nafter", fetch
    )
    assert out == "before\n[image attached: /tmp/shot.png]\nafter"
    (block,) = blocks
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"
    Image.open(io.BytesIO(base64.b64decode(block["source"]["data"])))


async def test_fetch_failure_becomes_note():
    async def fetch(path: str) -> bytes:
        raise RuntimeError("no such file")

    out, blocks = await extract_image_blocks("HYPERGOLIC_IMAGE:/tmp/x.png", fetch)
    assert blocks == []
    assert "no such file" in out


async def test_unsupported_extension():
    out, blocks = await extract_image_blocks("HYPERGOLIC_IMAGE:/tmp/x.pdf", _fail_fetch)
    assert blocks == []
    assert "unsupported extension" in out


async def test_image_cap():
    png = _png_bytes()

    async def fetch(path: str) -> bytes:
        return png

    stdout = "\n".join(f"HYPERGOLIC_IMAGE:/tmp/{i}.png" for i in range(MAX_IMAGES + 2))
    out, blocks = await extract_image_blocks(stdout, fetch)
    assert len(blocks) == MAX_IMAGES
    assert out.count("skipped") == 2
