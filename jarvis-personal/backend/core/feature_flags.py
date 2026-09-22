import logging
import time

from backend.core.database import get_connection

logger = logging.getLogger(__name__)

FEATURE_DEFINITIONS = {
    "financial_writes": {
        "display_name": "Escrituras financieras",
        "safe_default_enabled": False,
        "message_es": "Los cambios financieros están pausados temporalmente. Tus datos guardados siguen disponibles.",
        "message_en": "Financial changes are temporarily paused. Your saved data remains available.",
    },
    "gmail_automation": {
        "display_name": "Automatización Gmail",
        "safe_default_enabled": False,
        "message_es": "La automatización de Gmail está en mantenimiento temporal.",
        "message_en": "Gmail automation is temporarily under maintenance.",
    },
    "vip_intelligence": {
        "display_name": "Inteligencia VIP",
        "safe_default_enabled": True,
        "message_es": "La inteligencia VIP está en mantenimiento temporal.",
        "message_en": "VIP intelligence is temporarily under maintenance.",
    },
    "advanced_reports": {
        "display_name": "Reportes avanzados",
        "safe_default_enabled": True,
        "message_es": "Los reportes avanzados están en mantenimiento temporal.",
        "message_en": "Advanced reports are temporarily under maintenance.",
    },
    "store_billing": {
        "display_name": "Billing de tienda",
        "safe_default_enabled": False,
        "message_es": "Las compras y restauraciones están pausadas temporalmente.",
        "message_en": "Purchases and restores are temporarily paused.",
    },
}

_FLAG_CACHE = None
_FLAG_CACHE_UNTIL = 0.0
_CACHE_SECONDS = 30


def _fallback_flags():
    return {
        key: {
            "flag_key": key,
            "display_name": definition["display_name"],
            "enabled": definition["safe_default_enabled"],
            "safe_default_enabled": definition["safe_default_enabled"],
            "disabled_message_es": definition["message_es"],
            "disabled_message_en": definition["message_en"],
            "source": "safe_default",
        }
        for key, definition in FEATURE_DEFINITIONS.items()
    }


def clear_feature_flag_cache():
    global _FLAG_CACHE, _FLAG_CACHE_UNTIL
    _FLAG_CACHE = None
    _FLAG_CACHE_UNTIL = 0.0


def load_feature_flags(*, force: bool = False):
    global _FLAG_CACHE, _FLAG_CACHE_UNTIL
    now = time.monotonic()
    if not force and _FLAG_CACHE is not None and now < _FLAG_CACHE_UNTIL:
        return _FLAG_CACHE

    flags = _fallback_flags()
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """SELECT flag_key,display_name,enabled,safe_default_enabled,
                          disabled_message_es,disabled_message_en,updated_at
                   FROM app_feature_flags ORDER BY flag_key"""
            ).fetchall()
        for row in rows:
            if row["flag_key"] in flags:
                flags[row["flag_key"]] = {**row, "source": "database"}
    except Exception:
        logger.exception("Feature flag lookup failed; using safe defaults")

    _FLAG_CACHE = flags
    _FLAG_CACHE_UNTIL = now + _CACHE_SECONDS
    return flags


def user_feature_flags():
    return {
        "flags": list(load_feature_flags().values()),
        "cache_seconds": _CACHE_SECONDS,
    }


def _request_flag(method: str, path: str):
    method = method.upper()
    if path.startswith("/user-product/vip/gmail"):
        return "gmail_automation"
    if path.startswith("/product-ops/billing/store"):
        return "store_billing"
    if path.startswith("/user-product/vip/"):
        return "vip_intelligence"
    if path.startswith("/reports") or path.startswith("/user-product/basic/reports"):
        return "advanced_reports"
    if method in {"POST", "PUT", "PATCH", "DELETE"} and path.startswith((
        "/user-product/finance/", "/user-product/goals", "/user-product/savings-plans",
        "/user-product/transactions", "/user-product/free/movements",
        "/user-product/financial-situation",
    )):
        return "financial_writes"
    return None


def disabled_feature_for_request(method: str, path: str, user: dict | None = None):
    if user and user.get("role") in {"owner", "admin"}:
        return None
    flag_key = _request_flag(method, path)
    if not flag_key:
        return None
    flag = load_feature_flags().get(flag_key) or _fallback_flags()[flag_key]
    return None if flag["enabled"] else flag
