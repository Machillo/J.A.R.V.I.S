"""The pinned pypdf really extracts statement text, and a broken PDF never stops the batch.

Mail PDFs are untrusted input (pypdf is pinned for its security fixes). These tests run the
real library on synthetic bytes built here: no bank document, no network.
"""
import base64

from backend.email_monitor import gmail_content


def _pdf_with_text(text: str) -> bytes:
    """A minimal valid one-page PDF whose content stream draws ``text`` (Helvetica)."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


def _service(payloads: dict[str, bytes]):
    class Attachments:
        def get(self, **kwargs):
            data = base64.urlsafe_b64encode(payloads[kwargs["id"]]).decode()
            return type("E", (), {"execute": lambda self: {"data": data}})()

    return type("S", (), {"users": lambda self: type("U", (), {"messages": lambda self: type("M", (), {
        "attachments": lambda self: Attachments()})()})()})()


def _attachment(attachment_id: str) -> dict:
    return {"filename": f"{attachment_id}.pdf", "attachment_id": attachment_id, "mime_type": "application/pdf", "size": 900}


def test_statement_text_is_extracted_by_the_pinned_pypdf():
    service = _service({"ok": _pdf_with_text("Saldo final 12500.00 CRC")})
    text, names = gmail_content.extract_pdf_attachment_text(service, "m-1", [_attachment("ok")])
    assert "Saldo final 12500.00 CRC" in text
    assert text.startswith("[PDF ok.pdf]") and names == ["ok.pdf"]


def test_a_truncated_or_garbage_pdf_is_skipped_and_the_next_one_still_reads():
    good = _pdf_with_text("Monto 3000.00")
    payloads = {"cut": good[: len(good) // 2], "junk": b"%PDF-1.7\n\x00\xff not a pdf", "ok": good}
    text, names = gmail_content.extract_pdf_attachment_text(
        _service(payloads), "m-2", [_attachment("cut"), _attachment("junk"), _attachment("ok")]
    )
    assert "Monto 3000.00" in text
    assert names == ["cut.pdf", "junk.pdf", "ok.pdf"]
