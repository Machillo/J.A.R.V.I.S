"""Whose mailbox a bank email is parsed for.

The shared parser (``parser.py``) serves every DINCR account. Knowing who the
account holder is (their own name on a SINPE receipt, their own accounts in a
transfer) changes how a movement is described, so that identity must come from
the caller's own account/workspace, never from another account.

``NEUTRAL`` is the default: a caller that forgets to pass an identity gets no
personal context at all, never the Owner's. Users and the Owner's standard
mailbox flow pass ``for_account_holder(display_name)``; internal-transfer
ownership is then resolved per workspace by Financial Identity
(``user_product/candidate_resolution.py``). Only the retired Owner-only
``email_monitor`` paths (manual text scan) use ``owner_legacy_identity()``,
whose private accounts and contacts are read from Owner configuration, not
from source code.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


def _key(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass(frozen=True)
class ParserIdentity:
    # Names that denote the mailbox holder (a SINPE from/to them is their own).
    holder_names: tuple[str, ...] = ()
    # Known people whose incoming payments settle receivables.
    receivable_contacts: tuple[str, ...] = ()
    # Own accounts: full IBAN -> label, and account last4 -> label.
    own_account_ibans: dict[str, str] = field(default_factory=dict)
    own_account_aliases: dict[str, str] = field(default_factory=dict)

    @property
    def own_account_last4(self) -> dict[str, str]:
        return {iban[-4:]: label for iban, label in self.own_account_ibans.items()}

    def _match(self, raw: str, names: tuple[str, ...], *, prefix: bool) -> str | None:
        clean = _key(raw)
        for name in names:
            key = _key(name)
            # Whole words only: "Ana" must not match inside "Mariana".
            start = "^" if prefix else r"(?<!\w)"
            pattern = start + re.escape(key) + r"(?!\w)"
            if len(key) >= 3 and re.search(pattern, clean):
                return name
        return None

    def person(self, raw: str | None, *, prefix: bool = False) -> str:
        """Canonical name for a person mentioned in an email of this mailbox."""
        text = re.sub(r"[_\s]+", " ", raw or "").strip(" :")
        if not text:
            return ""
        return (
            self._match(text, self.holder_names, prefix=prefix)
            or self._match(text, self.receivable_contacts, prefix=prefix)
            or text.title()
        )

    def is_holder(self, name: str | None) -> bool:
        return bool(name) and _key(name) in {_key(item) for item in self.holder_names}

    def is_receivable_contact(self, name: str | None) -> bool:
        return bool(name) and _key(name) in {_key(item) for item in self.receivable_contacts}


NEUTRAL = ParserIdentity()
_current: ContextVar[ParserIdentity] = ContextVar("parser_identity", default=NEUTRAL)


def current_identity() -> ParserIdentity:
    return _current.get()


@contextmanager
def use_identity(identity: ParserIdentity | None) -> Iterator[ParserIdentity]:
    token = _current.set(identity or NEUTRAL)
    try:
        yield _current.get()
    finally:
        _current.reset(token)


def for_account_holder(display_name: str | None) -> ParserIdentity:
    """The holder's own name (full and first) from their DINCR account; nothing else."""
    full = re.sub(r"\s+", " ", display_name or "").strip()
    names = [name for name in (full, full.split(" ")[0] if full else "") if len(name) >= 3]
    return ParserIdentity(holder_names=tuple(dict.fromkeys(sorted(names, key=len, reverse=True))))


def _env_mapping(name: str) -> dict[str, str]:
    try:
        value = json.loads(os.getenv(name, "{}") or "{}")
    except json.JSONDecodeError:
        return {}
    return {str(key): str(label) for key, label in value.items()} if isinstance(value, dict) else {}


def _env_list(name: str) -> tuple[str, ...]:
    try:
        value = json.loads(os.getenv(name, "[]") or "[]")
    except json.JSONDecodeError:
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip()) if isinstance(value, list) else ()


def owner_legacy_identity() -> ParserIdentity:
    """Owner-only legacy email_monitor context, from Owner configuration (env)."""
    holder = for_account_holder(os.getenv("OWNER_DISPLAY_NAME", ""))
    return ParserIdentity(
        holder_names=holder.holder_names,
        receivable_contacts=_env_list("JARVIS_RECEIVABLE_CONTACTS"),
        own_account_ibans=_env_mapping("JARVIS_OWN_ACCOUNT_IBANS"),
        own_account_aliases=_env_mapping("JARVIS_OWN_ACCOUNT_ALIASES"),
    )
