import base64
import io

from PIL import Image

ANTHROPIC_MAX_BYTES = 3_800_000  # ~3.8MB to leave headroom under 4MB
MAX_DIMENSION = 2048
SUPPORTED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
SUPPORTED_DOCUMENT_TYPES = {"application/pdf"}


def process_pdf(data: bytes) -> str:
    return base64.standard_b64encode(data).decode("ascii")


def process_image(data: bytes, media_type: str) -> tuple[str, str]:
    if media_type == "image/gif":
        encoded = base64.standard_b64encode(data).decode("ascii")
        if len(data) <= ANTHROPIC_MAX_BYTES:
            return encoded, media_type
        raise ValueError("GIF too large and cannot be resized")

    img = Image.open(io.BytesIO(data))

    if img.mode in ("RGBA", "P") and media_type == "image/jpeg":
        img = img.convert("RGB")
    elif img.mode == "P":
        img = img.convert("RGBA")

    img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    output_format = "JPEG" if media_type == "image/jpeg" else "PNG"
    output_media = "image/jpeg" if output_format == "JPEG" else "image/png"

    quality = 95
    while quality >= 20:
        buf = io.BytesIO()
        save_kwargs: dict = {"format": output_format}
        if output_format == "JPEG":
            save_kwargs["quality"] = quality
            save_kwargs["optimize"] = True
        img.save(buf, **save_kwargs)
        raw = buf.getvalue()
        if len(raw) <= ANTHROPIC_MAX_BYTES:
            return base64.standard_b64encode(raw).decode("ascii"), output_media
        quality -= 10

    for scale in [0.75, 0.5, 0.25]:
        new_size = (int(img.width * scale), int(img.height * scale))
        scaled = img.resize(new_size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        save_kwargs = {"format": output_format}
        if output_format == "JPEG":
            save_kwargs["quality"] = 60
            save_kwargs["optimize"] = True
        scaled.save(buf, **save_kwargs)
        raw = buf.getvalue()
        if len(raw) <= ANTHROPIC_MAX_BYTES:
            return base64.standard_b64encode(raw).decode("ascii"), output_media

    raise ValueError("Unable to compress image below size limit")
