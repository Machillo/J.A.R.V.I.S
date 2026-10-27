"""Shared fixtures for the user_product unit tests.

These tests drive mail reading through fake connections that model a plan, not the stored Owner
identity. While DINCR's Google OAuth app is in testing, reading is limited to the verified Owner
(gmail_service.MAIL_READING_OWNER_ONLY); that rule is proven on a real PostgreSQL in
backend/tests/test_mail_monitor_owner_only_pg.py. Here the reading paths keep their plan rule,
the one they return to when reading reopens, so their behavior stays covered meanwhile.
"""
import pytest

from backend.user_product import gmail_service, microsoft_mail, routes


@pytest.fixture(autouse=True)
def mail_reading_follows_the_plan(monkeypatch):
    # Looked up at call time, so a test that patches _has_active_vip_access still decides.
    monkeypatch.setattr(gmail_service, "mail_reading_allowed",
                        lambda conn, account_id, workspace_id=None: gmail_service._has_active_vip_access(conn, account_id))
    monkeypatch.setattr(microsoft_mail, "mail_reading_allowed",
                        lambda conn, account_id, workspace_id=None: microsoft_mail._has_active_vip_access(conn, account_id))
    # Routes: the plan check is require_feature("gmail_automation"), which these tests drive.
    monkeypatch.setattr(routes, "require_mail_reading", lambda: None)
