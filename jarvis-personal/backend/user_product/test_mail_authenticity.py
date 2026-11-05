from backend.user_product import mail_authenticity, owner_pensions
from backend.user_product.test_owner_pensions import NAMES, SENDER, SUBJECT, TEXT

GOOGLE = "mx.google.com; "


def test_only_clear_evidence_of_forgery_rejects():
    assert mail_authenticity.forged([GOOGLE + "dkim=fail; spf=fail; dmarc=fail"], "mx.google.com")
    assert mail_authenticity.forged([GOOGLE + "spf=softfail smtp.mailfrom=x"], "mx.google.com")
    assert not mail_authenticity.forged([GOOGLE + "dkim=pass; spf=pass; dmarc=pass"], "mx.google.com")
    # Forwarding breaks SPF, a valid signature still proves the sender.
    assert not mail_authenticity.forged([GOOGLE + "dkim=pass; spf=fail"], "mx.google.com")
    assert not mail_authenticity.forged([], "mx.google.com")
    assert not mail_authenticity.forged([GOOGLE + "spf=none"], "mx.google.com")


def test_a_header_written_by_the_sender_does_not_count():
    assert not mail_authenticity.forged(["evil.example; dmarc=fail"], "mx.google.com")
    assert mail_authenticity.forged([GOOGLE + "dmarc=fail", "evil.example; dmarc=pass"], "mx.google.com")


def test_a_forged_sender_is_no_approved_sender():
    from backend.user_product import gmail_service

    assert not gmail_service.bank_sender_allowed(mail_authenticity.UNVERIFIED_SENDER)
    assert not gmail_service.ccss_sender_allowed(mail_authenticity.UNVERIFIED_SENDER)


def test_a_statement_from_the_future_is_refused():
    future = [NAMES[0].replace("2026", "2099", 1)] if "2026" in NAMES[0] else ["EstadoCta_1_209912_x.pdf"]
    assert owner_pensions.parse_statement(SUBJECT, SENDER, TEXT, future, "2026-10-10T12:00:00+00:00") is None
    assert owner_pensions.parse_statement(SUBJECT, SENDER, TEXT, NAMES, None) is None
