import asyncio

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from hypergolic.attachments.processing import (
    SUPPORTED_DOCUMENT_TYPES,
    SUPPORTED_MEDIA_TYPES,
    process_image,
    process_pdf,
)

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB
# Base64 inflates ~4/3x and Bedrock caps request bodies well below Anthropic's
# 32MB, so PDFs get a tighter raw-byte limit than images (which are recompressed).
MAX_PDF_BYTES = 10 * 1024 * 1024


class AttachmentResponse(BaseModel):
    type: str = "image"
    source: dict[str, str]


@router.post("/upload", response_model=AttachmentResponse)
async def upload_attachment(file: UploadFile = File(...)):
    content_type = file.content_type or "application/octet-stream"
    if content_type not in SUPPORTED_MEDIA_TYPES | SUPPORTED_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported media type: {content_type}. Supported: {', '.join(sorted(SUPPORTED_MEDIA_TYPES | SUPPORTED_DOCUMENT_TYPES))}",
        )

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    if content_type in SUPPORTED_DOCUMENT_TYPES:
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"PDF too large. Maximum size is {MAX_PDF_BYTES // (1024 * 1024)} MB.",
            )
        b64_data = await asyncio.to_thread(process_pdf, data)
        return AttachmentResponse(
            type="document",
            source={"type": "base64", "media_type": content_type, "data": b64_data},
        )

    try:
        b64_data, final_media_type = await asyncio.to_thread(process_image, data, content_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return AttachmentResponse(
        type="image",
        source={
            "type": "base64",
            "media_type": final_media_type,
            "data": b64_data,
        },
    )
