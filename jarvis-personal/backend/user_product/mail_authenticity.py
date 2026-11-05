"""Mail whose sender the receiving provider proved forged is not treated as bank or CCSS mail.

The From address alone can be faked, and some of this mail is saved without review. Only clear
evidence of forgery rejects a message: a provider that reports nothing keeps today's behavior, so
real notices are never lost because a header is missing. Deterministic; no content is logged.
"""
from __future__ import annotations

import re

UNVERIFIED_SENDER = "unverified@invalid.invalid"
_RESULT = re.compile(r"\b(dmarc|dkim|spf)\s*=\s*([a-z]+)", re.I)


def forged(authentication_results: list[str], authserv_id: str | None = None) -> bool:
    """True when the provider's own verdict says the sender was forged.

    An attacker can write its own header further down the message, so only the first one counts,
    the one the receiving provider added, and only if it names that provider when it is known.
    """
    if not authentication_results:
        return False
    verdict = authentication_results[0]
    if authserv_id and not verdict.strip().lower().startswith(authserv_id):
        return False
    found: dict[str, set[str]] = {}
    for method, result in _RESULT.findall(verdict):
        found.setdefault(method.lower(), set()).add(result.lower())
    if "fail" in found.get("dmarc", set()):
        return True
    return "pass" not in found.get("dkim", set()) and bool(found.get("spf", set()) & {"fail", "softfail"})
