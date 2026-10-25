"""Tests for hypergolic.attachments.processing."""

import base64
import io

import pytest
from PIL import Image

from hypergolic.attachments.processing import (
    ANTHROPIC_MAX_BYTES,
    SUPPORTED_MEDIA_TYPES,
    process_image,
)


def _make_image_bytes(
    mode: str = "RGB",
    size: tuple[int, int] = (100, 100),
    color: str | tuple = "red",
    fmt: str = "PNG",
) -> bytes:
    """Create a PIL image and return its bytes."""
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def _decode(encoded: str) -> bytes:
    return base64.standard_b64decode(encoded)


def test_gif_small_passthrough():
    """A small GIF is returned as-is."""
    # Tiny 1x1 GIF
    gif_bytes = (
        b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\x00\x00\x00\x00\x00!"
        b"\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01"
        b"\x00\x00\x02\x02D\x01\x00;"
    )
    assert len(gif_bytes) < ANTHROPIC_MAX_BYTES

    encoded, media_type = process_image(gif_bytes, "image/gif")
    assert media_type == "image/gif"
    assert _decode(encoded) == gif_bytes


def test_gif_large_raises():
    """A GIF exceeding the max size raises ValueError."""
    # Craft fake "GIF" bytes that exceed the limit
    big_gif = b"GIF89a" + b"X" * (ANTHROPIC_MAX_BYTES + 1)
    with pytest.raises(ValueError, match="GIF too large"):
        process_image(big_gif, "image/gif")


def test_jpeg_small_image_succeeds():
    """A small JPEG image is processed and returned as base64."""
    jpeg_bytes = _make_image_bytes(fmt="JPEG")
    encoded, media_type = process_image(jpeg_bytes, "image/jpeg")
    assert media_type == "image/jpeg"
    decoded = _decode(encoded)
    assert len(decoded) > 0
    # Verify it is a valid JPEG
    img = Image.open(io.BytesIO(decoded))
    assert img.format == "JPEG"


def test_jpeg_output_media_type():
    jpeg_bytes = _make_image_bytes(fmt="JPEG")
    _, media_type = process_image(jpeg_bytes, "image/jpeg")
    assert media_type == "image/jpeg"


def test_png_small_image_succeeds():
    png_bytes = _make_image_bytes(fmt="PNG")
    encoded, media_type = process_image(png_bytes, "image/png")
    assert media_type == "image/png"
    decoded = _decode(encoded)
    img = Image.open(io.BytesIO(decoded))
    assert img.format == "PNG"


def test_png_output_is_base64_string():
    png_bytes = _make_image_bytes(fmt="PNG")
    encoded, _ = process_image(png_bytes, "image/png")
    assert isinstance(encoded, str)
    # Must be valid base64
    base64.standard_b64decode(encoded)  # no exception


def test_rgba_with_jpeg_converts_to_rgb():
    """An RGBA image with JPEG media type is converted to RGB (no alpha channel)."""
    # Save RGBA as PNG first (JPEG can't hold RGBA), then pass as image/jpeg media type
    img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")  # save as PNG to get valid bytes with RGBA
    rgba_bytes = buf.getvalue()

    encoded, media_type = process_image(rgba_bytes, "image/jpeg")
    assert media_type == "image/jpeg"
    decoded = _decode(encoded)
    out_img = Image.open(io.BytesIO(decoded))
    # Should be JPEG (RGB), no RGBA
    assert out_img.mode in ("RGB", "L")


def test_p_mode_with_jpeg_converts_to_rgb():
    """A palette (P) mode image with JPEG media type is converted to RGB."""
    img = Image.new("P", (50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")  # P mode can only be saved as PNG
    p_bytes = buf.getvalue()

    encoded, media_type = process_image(p_bytes, "image/jpeg")
    assert media_type == "image/jpeg"
    decoded = _decode(encoded)
    out_img = Image.open(io.BytesIO(decoded))
    assert out_img.mode in ("RGB", "L")


def test_p_mode_with_png_converts_to_rgba():
    """A palette (P) mode image with PNG media type is converted to RGBA."""
    img = Image.new("P", (50, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    p_bytes = buf.getvalue()

    encoded, media_type = process_image(p_bytes, "image/png")
    assert media_type == "image/png"
    decoded = _decode(encoded)
    out_img = Image.open(io.BytesIO(decoded))
    # Should be RGBA after conversion
    assert out_img.mode == "RGBA"


def test_large_image_is_resized_within_limits():
    """A very large PNG image is compressed/resized to fit under the byte limit."""
    # Create a large (3000x3000) image — raw would be huge, will need compression
    img = Image.new("RGB", (3000, 3000), "blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    large_bytes = buf.getvalue()

    encoded, media_type = process_image(large_bytes, "image/png")
    assert media_type == "image/png"
    decoded = _decode(encoded)
    assert len(decoded) <= ANTHROPIC_MAX_BYTES


def test_large_jpeg_is_compressed_within_limits():
    """A large JPEG image is compressed to fit under the byte limit."""
    img = Image.new("RGB", (3000, 3000), "green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=100)
    large_bytes = buf.getvalue()

    encoded, media_type = process_image(large_bytes, "image/jpeg")
    assert media_type == "image/jpeg"
    decoded = _decode(encoded)
    assert len(decoded) <= ANTHROPIC_MAX_BYTES


def test_supported_media_types_contains_expected():
    assert "image/jpeg" in SUPPORTED_MEDIA_TYPES
    assert "image/png" in SUPPORTED_MEDIA_TYPES
    assert "image/gif" in SUPPORTED_MEDIA_TYPES
    assert "image/webp" in SUPPORTED_MEDIA_TYPES


def test_anthropic_max_bytes_reasonable():
    # Should be a positive integer below 4MB
    assert 0 < ANTHROPIC_MAX_BYTES < 4_000_000
