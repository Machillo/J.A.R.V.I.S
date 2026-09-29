"""AI lab: an interface and a deterministic fake. No real provider is wired.

DINCR has no generative-AI runtime for user data (CLAUDE.md §4.E). Labs may
explore ideas only on synthetic data and only through this interface. Adding a
real provider needs, before any code: explicit authorization, a known cost, a
privacy review, and secrets kept outside the repository. ``provider()`` refuses
every name except the fake, and labs/tests/test_ai_lab.py fails if an AI SDK or
provider endpoint appears anywhere under labs/.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Categorization:
    category: str
    confidence: float
    rule: str


class AIProvider(Protocol):
    name: str

    def categorize(self, description: str) -> Categorization: ...

    def explain(self, facts: dict[str, str]) -> str: ...


_KEYWORDS = (
    ("super", "Alimentación"), ("cafe", "Alimentación"), ("farmacia", "Salud"), ("gasolin", "Transporte"),
    ("taxi", "Transporte"), ("hosting", "Servicios"), ("internet", "Servicios"), ("cine", "Entretenimiento"),
    ("libreria", "Educación"), ("veterinaria", "Mascotas"),
)


class FakeAIProvider:
    """Deterministic stand-in: keyword rules, reproducible output, no network, no model."""

    name = "fake"

    def categorize(self, description: str) -> Categorization:
        text = (description or "").lower()
        for keyword, category in _KEYWORDS:
            if keyword in text:
                return Categorization(category, 0.9, f"keyword:{keyword}")
        # Stable pseudo-confidence for "unknown", so tests can pin it.
        digest = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:4], 16)
        return Categorization("Otros", round(0.3 + (digest % 20) / 100, 2), "fallback")

    def explain(self, facts: dict[str, str]) -> str:
        return " ".join(f"{key}: {facts[key]}." for key in sorted(facts))


def provider(name: str = "fake") -> AIProvider:
    if name != "fake":
        raise PermissionError(
            f"AI provider {name!r} is not available in Labs: a real provider needs authorization, "
            "a known cost, a privacy review and secrets outside the repository (docs/labs.md)."
        )
    return FakeAIProvider()
