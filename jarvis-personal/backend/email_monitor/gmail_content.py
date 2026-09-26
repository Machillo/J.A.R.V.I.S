from __future__ import annotations

import base64
import html
import re
from io import BytesIO
from typing import Any

# Mail is third-party input: every bound applies before parsing, whatever the sender.
MAX_BODY_CHARS = 256_000
MAX_PDF_ATTACHMENTS = 3
MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_PDF_TEXT_CHARS = 200_000
_SPACE = re.compile(r"\s+")


def plain_text_from_html(raw: str | None) -> str:
    """Visible text of a mail body, in one linear pass and bounded size.

    Tags are removed with str.find, never with a regex: a lazy DOTALL pattern
    ("<script.*?</script>") and even "<[^>]*>" rescan the rest of the text from
    every unterminated "<", which is quadratic on hostile mail and holds the GIL.
    An unterminated tag or script/style block drops the rest of the text.
    """
    text = (raw or "")[:MAX_BODY_CHARS]
    lower, kept, position, length = text.lower(), [], 0, len(text)
    while position < length:
        start = text.find("<", position)
        if start < 0:
            kept.append(text[position:])
            break
        kept.append(text[position:start])
        end = text.find(">", start + 1)
        if end < 0:
            break
        tag = lower[start + 1:end].split(None, 1)
        name = tag[0] if tag else ""
        if name in ("script", "style"):
            close = lower.find(f"</{name}", end + 1)
            close_end = text.find(">", close + 1) if close >= 0 else -1
            if close_end < 0:
                break
            position = close_end + 1
        else:
            position = end + 1
        kept.append(" ")
    return _SPACE.sub(" ", html.unescape("".join(kept))).strip()


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

    parsed = 0
    for attachment in attachments:
        filename = attachment.get("filename") or ""
        attachment_id = attachment.get("attachment_id")
        mime_type = attachment.get("mime_type") or ""
        if filename:
            names.append(filename)
        if not attachment_id or ("pdf" not in mime_type.lower() and not filename.lower().endswith(".pdf")):
            continue
        if parsed >= MAX_PDF_ATTACHMENTS or int(attachment.get("size") or 0) > MAX_PDF_BYTES:
            continue
        try:
            encoded = gmail_service.users().messages().attachments().get(
                userId="me", messageId=message_id, id=attachment_id
            ).execute().get("data")
            if not encoded or len(encoded) > MAX_PDF_BYTES * 4 // 3 + 4:
                continue
            parsed += 1
            reader = PdfReader(BytesIO(base64.urlsafe_b64decode(encoded.encode("utf-8"))))
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:8]).strip()
            if text:
                texts.append(f"[PDF {filename}]\n{text}")
        except Exception:
            continue
    return "\n".join(texts)[:MAX_PDF_TEXT_CHARS], names
