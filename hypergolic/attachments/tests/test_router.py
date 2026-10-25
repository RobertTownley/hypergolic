"""Tests for hypergolic.attachments.router."""

from unittest.mock import patch


def test_upload_image_too_large(api_client):
    oversized_data = b"x" * (20 * 1024 * 1024 + 1)
    resp = api_client.post(
        "/api/attachments/upload",
        files={"file": ("big.png", oversized_data, "image/png")},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_upload_image_processing_error(api_client):
    with patch(
        "hypergolic.attachments.router.process_image",
        side_effect=ValueError("corrupt image data"),
    ):
        resp = api_client.post(
            "/api/attachments/upload",
            files={"file": ("bad.png", b"\x89PNG\r\n\x1a\nfakedata", "image/png")},
        )
    assert resp.status_code == 400
    assert "corrupt image data" in resp.json()["detail"]


def test_upload_pdf(api_client):
    import base64

    data = b"%PDF-1.4 fake pdf bytes"
    resp = api_client.post(
        "/api/attachments/upload",
        files={"file": ("doc.pdf", data, "application/pdf")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "document"
    assert body["source"]["media_type"] == "application/pdf"
    assert base64.standard_b64decode(body["source"]["data"]) == data


def test_upload_unsupported_type(api_client):
    resp = api_client.post(
        "/api/attachments/upload",
        files={"file": ("doc.docx", b"data", "application/msword")},
    )
    assert resp.status_code == 400
    assert "application/pdf" in resp.json()["detail"]


def test_upload_image_success(api_client):
    with patch(
        "hypergolic.attachments.router.process_image",
        return_value=("base64encodeddata", "image/png"),
    ):
        resp = api_client.post(
            "/api/attachments/upload",
            files={"file": ("test.png", b"\x89PNG\r\n\x1a\nfakedata", "image/png")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "image"
    assert data["source"]["type"] == "base64"
    assert data["source"]["media_type"] == "image/png"
    assert data["source"]["data"] == "base64encodeddata"


def test_upload_empty_file(api_client):
    resp = api_client.post(
        "/api/attachments/upload",
        files={"file": ("empty.png", b"", "image/png")},
    )
    assert resp.status_code == 400
    assert "Empty file" in resp.json()["detail"]


def test_upload_pdf_too_large(api_client):
    resp = api_client.post(
        "/api/attachments/upload",
        files={"file": ("big.pdf", b"x" * (10 * 1024 * 1024 + 1), "application/pdf")},
    )
    assert resp.status_code == 413
    assert "PDF too large" in resp.json()["detail"]
