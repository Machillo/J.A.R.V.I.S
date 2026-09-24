"""Ask a model for a declarative parser proposal and validate it deterministically."""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from backend.parser_discovery import PENDING
from backend.parser_discovery.sanitize import residual_risks

FIELDS = ("amount", "date", "description", "reference")
MAX_PATTERN = 300

SYSTEM = (
    "You design deterministic parsers for Costa Rican bank notification emails. "
    "Return ONLY a JSON object with keys: bank (string), sender_domains (list of domains), "
    "subject_pattern (Python regex), fields (object with optional keys amount, date, description, reference; "
    "each a Python regex with exactly one named group called value), currency_hint (CRC, USD or null), "
    "direction (object with income_keywords and expense_keywords lists), notes (string). "
    "Digits in the samples are masked as 9: write patterns for the shape, never for literal values. "
    "Never include personal data. Never write code."
)


def build_prompt(samples: list[str]) -> str:
    blocks = "\n\n".join(f"--- SAMPLE {index} ---\n{sample}" for index, sample in enumerate(samples, 1))
    return f"Propose one parser that fits all samples of this unknown format.\n\n{blocks}"


def _pattern(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_PATTERN:
        raise ValueError(f"{name}: missing or longer than {MAX_PATTERN} characters")
    compiled = re.compile(value)
    if name.startswith("fields.") and list(compiled.groupindex) != ["value"]:
        raise ValueError(f"{name}: needs exactly one named group 'value'")
    return value


def validate_proposal(raw: dict[str, Any], *, source_model: str) -> dict[str, Any]:
    """Keep only the declarative schema; the status is always PENDING, whatever the model says."""
    if not isinstance(raw, dict):
        raise ValueError("proposal must be an object")
    fields = raw.get("fields") or {}
    if not isinstance(fields, dict) or "amount" not in fields:
        raise ValueError("fields.amount is required")
    direction = raw.get("direction") or {}
    return {
        "status": PENDING,
        "bank": str(raw.get("bank") or "unknown")[:60],
        "sender_domains": [str(item).lower()[:120] for item in raw.get("sender_domains") or [] if isinstance(item, str)][:10],
        "subject_pattern": _pattern(raw.get("subject_pattern"), "subject_pattern"),
        "fields": {name: _pattern(fields[name], f"fields.{name}") for name in FIELDS if fields.get(name)},
        "currency_hint": raw.get("currency_hint") if raw.get("currency_hint") in {"CRC", "USD"} else None,
        "direction": {
            "income_keywords": [str(item)[:60] for item in direction.get("income_keywords") or []][:20],
            "expense_keywords": [str(item)[:60] for item in direction.get("expense_keywords") or []][:20],
        },
        "notes": str(raw.get("notes") or "")[:1000],
        "source_model": source_model,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved_by": None,
    }


def evaluate_proposal(proposal: dict[str, Any], sample: str) -> dict[str, Any]:
    """Run a proposal against one sample exactly as a deterministic parser would."""
    extracted = {}
    for name, pattern in proposal["fields"].items():
        match = re.search(pattern, sample, re.I | re.S)
        extracted[name] = match.group("value").strip() if match else None
    lowered = sample.lower()
    direction = "unknown"
    if any(word.lower() in lowered for word in proposal["direction"]["income_keywords"]):
        direction = "in"
    elif any(word.lower() in lowered for word in proposal["direction"]["expense_keywords"]):
        direction = "out"
    return {"fields": extracted, "direction": direction, "complete": extracted.get("amount") is not None}


def openai_sender(prompt: str) -> tuple[dict[str, Any], str]:
    """Send the sanitized prompt to OpenAI (Responses API). Requires explicit configuration."""
    if os.getenv("PARSER_DISCOVERY_ENABLED", "").strip().lower() != "true":
        raise RuntimeError("PARSER_DISCOVERY_ENABLED=true is required to contact the provider.")
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")
    model = os.getenv("PARSER_DISCOVERY_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "instructions": SYSTEM, "input": prompt, "max_output_tokens": 1500,
              "text": {"format": {"type": "json_object"}}, "store": False},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("output_text") or "".join(
        part.get("text", "") for item in payload.get("output") or [] if item.get("type") == "message"
        for part in item.get("content") or []
    )
    return json.loads(text), model


def propose(samples: list[str], sender: Callable[[str], tuple[dict[str, Any], str]] = openai_sender) -> dict[str, Any]:
    """Samples must already be sanitized; anything that still looks personal blocks the request."""
    for index, sample in enumerate(samples, 1):
        risks = residual_risks(sample)
        if risks:
            raise ValueError(f"sample {index} is not safe to send: {', '.join(risks)}")
    raw, model = sender(build_prompt(samples))
    proposal = validate_proposal(raw, source_model=model)
    proposal["evaluation"] = [evaluate_proposal(proposal, sample) for sample in samples]
    return proposal
