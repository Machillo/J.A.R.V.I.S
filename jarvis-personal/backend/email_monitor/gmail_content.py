from __future__ import annotations

import base64
from io import BytesIO
from typing import Any


def collect_attachments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return Gmail attachment metadata from a nested MIME payload."""
    attachments: list[dict[str, Any]] = []

    def walk(part: dict[str, Any]) -> None:
        filename = part.get("filename") or ""
        body = part.get("body") or {}
        attachment_id = body.get("attachmentId")
        if filename or attachment_id:
            attachments.append({
                "filename": filename,
                "attachment_id": attachment_id,
                "mime_type": part.get("mimeType", ""),
                "size": body.get("size"),
            })
        for child in part.get("parts") or []:
            walk(child)

    walk(payload or {})
    return attachments


def extract_pdf_attachment_text(
    gmail_service, message_id: str, attachments: list[dict[str, Any]]
) -> tuple[str, list[str]]:
    """Extract text from Gmail PDF attachments using the shared local parser."""
    texts: list[str] = []
    names: list[str] = []
    try:
        from pypdf import PdfReader
    except Exception:
        return "", [item.get("filename") or "" for item in attachments if item.get("filename")]

    for attachment in attachments:
        filename = attachment.get("filename") or ""
        attachment_id = attachment.get("attachment_id")
        mime_type = attachment.get("mime_type") or ""
        if filename:
            names.append(filename)
        if not attachment_id or ("pdf" not in mime_type.lower() and not filename.lower().endswith(".pdf")):
            continue
        try:
            encoded = gmail_service.users().messages().attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute().get("data")
            if not encoded:
                continue
            reader = PdfReader(BytesIO(base64.urlsafe_b64decode(encoded.encode("utf-8"))))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:8]).strip()
            if text:
                texts.append(f"[PDF {filename}]\n{text}")
        except Exception:
            continue
    return "\n".join(texts), names
