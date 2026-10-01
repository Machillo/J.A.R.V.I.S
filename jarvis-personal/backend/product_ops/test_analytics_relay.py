"""Native product analytics relay (contract v2) and its parity with every client.

The Capacitor app sends the v2 contract with posthog-js; the native iOS/Android apps send it to
POST /product-ops/analytics and this relay forwards it. One taxonomy, one privacy contract: these
tests fail when the backend, the Capacitor contract, Kotlin or Swift drift apart.
"""
import re
from pathlib import Path

import pytest

from backend.product_ops import analytics_relay as relay
from backend.product_ops import posthog_events
from backend.product_ops.models import AnalyticsEventIn

ROOT = Path(__file__).resolve().parents[2]
JS = (ROOT / "frontend/src/lib/analyticsContract.js").read_text(encoding="utf-8")
KOTLIN = (ROOT / "native/android/core/data/src/main/kotlin/com/dincr/data/Analytics.kt").read_text(encoding="utf-8")
KOTLIN_JARVIS = (ROOT / "native/android/core/data/src/main/kotlin/com/dincr/data/Jarvis.kt").read_text(encoding="utf-8")
SWIFT = (ROOT / "native/ios/DincrKit/Sources/DincrCore/Analytics.swift").read_text(encoding="utf-8")
SWIFT_JARVIS = (ROOT / "native/ios/DincrKit/Sources/DincrCore/Jarvis.swift").read_text(encoding="utf-8")

INSTALL = "0192f0c4-7b1a-4c3e-9a51-3f2b8d6e1a90"
SESSION = "0192f0c4-7b1a-4c3e-9a51-3f2b8d6e1a91"


def js_set(name: str) -> set[str]:
    body = re.search(rf"export const {name} = new Set\(\[(.*?)\]\);", JS, re.S).group(1)
    return set(re.findall(r'"([^"]+)"', body))


def js_categories() -> dict[str, set[str]]:
    body = re.search(r"const categories = \{(.*?)\n\};", JS, re.S).group(1)
    named = {"userScreens": js_set("userScreens"), "jarvisSections": js_set("jarvisSections"),
             "mailOAuthErrorCodes": js_set("mailOAuthErrorCodes"), "usefulActionTypes": js_useful_types()}
    result = {}
    for name, value in re.findall(r"^\s+([a-z_]+): (.+?),?$", body, re.M):
        literal = re.match(r"new Set\(\[(.*)\]\)", value)
        result[name] = set(re.findall(r'"([^"]+)"', literal.group(1))) if literal else named[value.rstrip(",")]
    return result


def js_rules() -> list[tuple[str, str, str]]:
    body = re.search(r"const usefulActionRules = \[(.*?)\n\];", JS, re.S).group(1)
    return [(m, p.replace("\\/", "/"), t) for m, p, t in re.findall(r'\["(\w+)", /(.+?)/, "([a-z_]+)"\]', body)]


def js_useful_types() -> set[str]:
    return {t for _, _, t in js_rules()} | {"mail_candidate_reviewed"}


def kotlin_rules():
    return re.findall(r'Rule\("(\w+)", """(.+?)""", "([a-z_]+)"\)', KOTLIN)


def swift_rules():
    return re.findall(r'Rule\(method: "(\w+)", pattern: #"(.+?)"#, actionType: "([a-z_]+)"\)', SWIFT)


# --- Parity: one contract for Capacitor, backend, Android and iOS -------------------------------

def test_backend_relay_mirrors_the_capacitor_contract():
    assert relay.USER_EVENTS == js_set("userEvents")
    assert relay.OWNER_EVENTS == js_set("ownerEvents")
    categories = js_categories()
    for name, values in relay.CLIENT_CATEGORIES.items():
        assert values == categories[name], name
    for name, values in relay.SERVER_CATEGORIES.items():
        assert values == categories[name], name
    assert set(relay.CLIENT_CATEGORIES) | set(relay.SERVER_CATEGORIES) == set(categories)
    assert relay.USEFUL_ACTION_TYPES == js_useful_types()


@pytest.mark.parametrize("rules", [kotlin_rules, swift_rules], ids=["android", "ios"])
def test_native_useful_action_rules_equal_the_capacitor_rules(rules):
    assert rules() == js_rules()
    assert len(js_rules()) >= 20


def test_native_events_screens_and_jarvis_sections_are_in_the_contract():
    contract_events = js_set("userEvents") | js_set("ownerEvents")
    kotlin_events = set(re.findall(r'"([^"]+)"', re.search(r"val EVENTS = setOf\((.*?)\)", KOTLIN, re.S).group(1)))
    swift_events = set(re.findall(r'"([^"]+)"', re.search(r"static let events: Set<String> = \[(.*?)\]", SWIFT, re.S).group(1)))
    assert kotlin_events == swift_events and kotlin_events <= contract_events
    screens = js_set("userScreens")
    kotlin_screens = re.findall(r'"[^"]+" to "([^"]+)"', re.search(r"val SCREENS = mapOf\((.*?)\)", KOTLIN, re.S).group(1))
    swift_screens = re.findall(r'"[^"]+": "([^"]+)"', re.search(r"static let screens: \[String: String\] = \[(.*?)\]", SWIFT, re.S).group(1))
    assert kotlin_screens and swift_screens and set(kotlin_screens) | set(swift_screens) <= screens
    sections = js_set("jarvisSections")
    kotlin_sections = set(re.findall(r'[A-Z_]+\("([a-z_]+)"\)', KOTLIN_JARVIS))
    swift_block = re.search(r"public enum Section: String.*?\{(.*?)public var id", SWIFT_JARVIS, re.S).group(1)
    swift_sections = {m[1] or m[0] for m in re.findall(r'(?:case|,)\s*(\w+)(?:\s*=\s*"([a-z_]+)")?', swift_block)}
    assert kotlin_sections and kotlin_sections == swift_sections and kotlin_sections <= sections


# --- Audience: decided by the server, never by the client ---------------------------------------

def event(name="screen_viewed", **properties):
    return {"event": name, "properties": properties, "install_id": INSTALL, "session_id": SESSION,
            "platform": "android", "app_version": "2.0.0", "build": "release"}


@pytest.mark.parametrize("plan", ["free", "basic", "vip"])
def test_users_send_users_events_with_the_servers_plan(plan):
    payload = relay.build_relay_payload(event(screen="overview", plan="vip", audience="owner", environment="staging"), "user", plan)
    assert payload["event"] == "screen_viewed" and payload["distinct_id"] == INSTALL
    assert payload["properties"]["audience"] == "user"
    assert payload["properties"]["plan"] == plan
    assert payload["properties"]["client"] == "native"
    assert payload["properties"]["screen"] == "overview"
    assert payload["properties"]["$process_person_profile"] is False and payload["properties"]["$geoip_disable"] is True
    assert relay.build_relay_payload(event("jarvis_section_viewed", jarvis_section="chat"), "user", plan) is None


def test_the_owner_sends_only_jarvis_metadata_and_no_plan():
    payload = relay.build_relay_payload(event("jarvis_section_viewed", jarvis_section="calendar"), "owner", None)
    assert payload["properties"]["audience"] == "owner" and "plan" not in payload["properties"]
    assert payload["properties"]["jarvis_section"] == "calendar"
    for name in ["app_opened", "screen_viewed", "useful_action", "mail_candidate_reviewed"]:
        assert relay.build_relay_payload(event(name), "owner", None) is None


def test_admin_unknown_plans_and_missing_legal_acceptance_send_nothing(monkeypatch):
    assert relay.build_relay_payload(event(), None, None) is None
    statements = []

    class Conn:
        def __init__(self, plan):
            self.plan = plan

        def execute(self, sql, params=()):
            statements.append(sql)
            return type("R", (), {"fetchone": lambda _self: {"code": self.plan} if self.plan else None})()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def run(user, plan="vip", legal_required=False):
        monkeypatch.setattr(relay, "get_connection", lambda: Conn(plan))
        monkeypatch.setattr(relay, "legal_status", lambda conn, account_id: {"required": legal_required})
        return relay.audience_of(user)

    assert run({"role": "admin", "account_id": "a"}) == (None, None)
    assert run({"role": "user", "account_id": "a"}, legal_required=True) == (None, None)
    assert run({"role": "owner", "account_id": "a"}, legal_required=True) == (None, None)
    assert run({"role": "user", "account_id": "a"}, plan="owner") == (None, None)
    assert run({"role": "user", "account_id": "a"}, plan=None) == (None, None)
    assert run({"role": "user"}) == (None, None)
    assert run({"role": "user", "account_id": "a"}, plan="basic") == ("user", "basic")
    assert run({"role": "owner", "account_id": "a"}) == ("owner", None)
    assert statements and all(sql.lstrip().upper().startswith("SELECT") for sql in statements), "the relay never writes"


# --- Privacy: closed values only, no identifiers ------------------------------------------------

HOSTILE = {
    "amount": "12500", "balance": "1", "salary": "1", "debt": "1", "email": "a@example.com", "name": "Ana",
    "iban": "CR05015202001026284066", "card": "4111111111111111", "sinpe": "88888888", "bank": "BAC",
    "subject": "Pago", "body": "Hola", "prompt": "cuanto gane", "text": "hola", "chat_message": "x",
    "calendar_title": "Cita", "account_id": "uuid", "workspace_id": "uuid", "user_id": "1",
    "screen": "/debts/42", "jarvis_section": "chat: pagar a Ana", "action_type": "transfer 5000",
    "decision": "accepted!", "$current_url": "https://x", "$set": "x", "$geoip_latitude": "9.9",
}


def test_hostile_properties_never_pass():
    assert relay.safe_client_properties(HOSTILE) == {}
    payload = relay.build_relay_payload({**event(), "properties": HOSTILE}, "user", "vip")
    assert set(payload["properties"]) == {"audience", "client", "platform", "environment", "plan", "app_version",
                                          "$session_id", "$process_person_profile", "$geoip_disable"}


def test_the_payload_carries_only_the_anonymous_install_id():
    payload = relay.build_relay_payload(event(screen="overview"), "user", "free")
    assert set(payload) == {"event", "distinct_id", "properties"}
    assert payload["distinct_id"] == INSTALL
    for bad in ["", "1234", "dincr_server_x", "a@example.com", INSTALL + "0"]:
        assert relay.build_relay_payload({**event(), "install_id": bad}, "user", "free") is None


def test_debug_builds_and_bad_versions_are_labelled_not_trusted(monkeypatch):
    monkeypatch.setenv("ANALYTICS_ENVIRONMENT", "production")
    assert relay.build_relay_payload(event(), "user", "free")["properties"]["environment"] == "production"
    assert relay.build_relay_payload({**event(), "build": "debug"}, "user", "free")["properties"]["environment"] == "development"
    payload = relay.build_relay_payload({**event(), "app_version": "2.0.0-rc.1", "session_id": "x"}, "user", "free")
    assert "app_version" not in payload["properties"] and "$session_id" not in payload["properties"]
    assert relay.build_relay_payload({**event(), "platform": "web"}, "user", "free") is None


def test_the_request_model_rejects_free_text_and_extra_fields():
    with pytest.raises(Exception):
        AnalyticsEventIn(**{**event(), "account_id": "x"})
    with pytest.raises(Exception):
        AnalyticsEventIn(**{**event(), "properties": {"screen": "x" * 41}})
    with pytest.raises(Exception):
        AnalyticsEventIn(**{**event(), "properties": {f"p{i}": "x" for i in range(9)}})
    with pytest.raises(Exception):
        AnalyticsEventIn(**{**event(), "event": "Screen Viewed"})
    assert AnalyticsEventIn(**event(screen="overview")).install_id == INSTALL


def test_relay_is_off_without_posthog_and_never_reveals_the_outcome(monkeypatch):
    sent = []
    monkeypatch.setattr(relay, "get_current_user", lambda: {"role": "user", "account_id": "a"})
    monkeypatch.setattr(relay, "capture_prepared_later", sent.append)
    monkeypatch.setattr(relay, "audience_of", lambda user: pytest.fail("no lookup when analytics is off"))
    monkeypatch.setattr(relay, "is_configured", lambda: False)
    assert relay.relay_event(event()) == {"status": "accepted"} and sent == []
    monkeypatch.setattr(relay, "is_configured", lambda: True)
    monkeypatch.setattr(relay, "audience_of", lambda user: (None, None))
    assert relay.relay_event(event()) == {"status": "accepted"} and sent == []
    monkeypatch.setattr(relay, "audience_of", lambda user: ("user", "vip"))
    assert relay.relay_event(event(screen="overview")) == {"status": "accepted"}
    assert [p["event"] for p in sent] == ["screen_viewed"]


def test_prepared_payloads_are_posted_with_the_server_key_only(monkeypatch):
    posted = []
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")

    class Response:
        def raise_for_status(self):
            return None

    monkeypatch.setattr(posthog_events.requests, "post", lambda url, json, timeout: posted.append((url, json)) or Response())
    assert posthog_events._relay_slots.acquire(blocking=False)
    posthog_events._send_prepared({"event": "screen_viewed", "distinct_id": INSTALL, "properties": {}})
    assert posted == [("https://us.i.posthog.com/capture/", {"api_key": "phc_test", "event": "screen_viewed", "distinct_id": INSTALL, "properties": {}})]


def test_a_flood_is_dropped_not_queued_without_limit(monkeypatch):
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")
    submitted = []
    monkeypatch.setattr(posthog_events, "_relay_executor", type("E", (), {"submit": lambda _self, fn, payload: submitted.append(payload)})())
    monkeypatch.setattr(posthog_events, "_relay_slots", posthog_events.threading.BoundedSemaphore(3))
    results = [posthog_events.capture_prepared_later({"event": "screen_viewed"}) for _ in range(5)]
    assert results == [True, True, True, False, False] and len(submitted) == 3


def test_the_relay_logs_no_identifier_or_property(monkeypatch, caplog):
    monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
    monkeypatch.setenv("POSTHOG_HOST", "https://us.i.posthog.com")

    def fail(*args, **kwargs):
        raise posthog_events.requests.ConnectionError(f"boom {INSTALL} overview")

    monkeypatch.setattr(posthog_events.requests, "post", fail)
    assert posthog_events._relay_slots.acquire(blocking=False)
    with caplog.at_level("DEBUG"):
        posthog_events._send_prepared({"event": "screen_viewed", "distinct_id": INSTALL, "properties": {"screen": "overview"}})
    assert caplog.text and INSTALL not in caplog.text and "overview" not in caplog.text


def test_the_route_is_authenticated_and_bound_to_the_strict_model():
    from backend import main
    from backend.product_ops import routes

    assert "/product-ops/analytics" not in main.PUBLIC_PATHS
    route = next(r for r in routes.router.routes if getattr(r, "path", "") == "/product-ops/analytics")
    assert route.methods == {"POST"}
    assert route.dependant.body_params[0].type_ is AnalyticsEventIn or route.dependant.body_params[0].field_info.annotation is AnalyticsEventIn


def test_app_version_is_strict_ascii_xyz():
    for bad in ["1.2.3" + chr(10), "１.２.３", "12345.0.0", "1.2", "1.2.3-rc.1"]:
        assert "app_version" not in relay.build_relay_payload({**event(), "app_version": bad}, "user", "free")["properties"], bad
