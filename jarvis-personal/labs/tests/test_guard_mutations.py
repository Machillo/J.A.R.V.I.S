"""Mutation tests: weaken a guard and the adversarial battery must notice.

Each mutant is the real guard source with one protection removed, loaded as a
separate module. If the battery still refused everything with a protection
gone, that protection would be untested. Every mutant must be "killed".
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from labs.tests import adversarial

LABS = Path(__file__).resolve().parents[1]

GUARD_MUTANTS = {
    "no loopback check": ("if not (_is_loopback(host) or _is_local_socket_dir(host)):", "if False:"),
    "no production markers": ("    if markers:\n", "    if False:\n"),
    "no forbidden settings": ("    if forbidden:\n", "    if False:\n"),
    "no DINCR_ENV check": ('if environ.get("DINCR_ENV") != LABS_ENV_VALUE:', "if False:"),
    "DINCR_ENV not exact": ('environ.get("DINCR_ENV") != LABS_ENV_VALUE', 'environ.get("DINCR_ENV", "").lower() not in ("labs", "production", "development")'),
    "no DATABASE_URL mismatch check": ("if backend_dsn and backend_dsn.strip() != dsn.strip():", "if False:"),
    "no database name prefix": ("if not name.startswith(LABS_DB_PREFIX):", "if False:"),
    "no libpq variables check": ("    if libpq:\n", "    if False:\n"),
    "no proxy check": ("    if proxies:\n", "    if False:\n"),
    "no query key allowlist": ("    if unexpected:\n", "    if False:\n"),
    "no query hosts": ('    for value in query.get("host", []) + query.get("hostaddr", []):', "    for value in []:"),
    "multi-host read like urllib": ("    user, hosts = _netloc_hosts(parts.netloc)",
                                    "    user, hosts = unquote(parts.username or ''), [parts.hostname] if parts.hostname else []"),
    "no pooler-login check": ('    if re.fullmatch(r"postgres\\.[a-z0-9]{15,}", user):', "    if False:"),
    "any scheme": ('    if parts.scheme not in {"postgresql", "postgres"}:', "    if False:"),
    "credential pattern neutered": ('r"(SECRET|PASSWORD|PASSWD|TOKEN|PRIVATE_KEY|API_KEY|SERVICE_ACCOUNT|WEBHOOK|CREDENTIAL|DSN$|_JWT)"', 'r"(NEVER_MATCHES_ANYTHING)"'),
    "no prefix families": ("or upper.startswith(FORBIDDEN_PREFIXES) ", ""),
}


def _load(source: str, name: str):
    spec = importlib.util.spec_from_loader(name, loader=None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    exec(compile(source, name, "exec"), module.__dict__)  # noqa: S102 (test-only load of a mutated local file)
    return module


def _survivors(guard) -> list[str]:
    """Battery cases the (possibly mutated) guard fails to refuse."""
    escaped = []
    for label, dsn in adversarial.REFUSED_DSNS.items():
        try:
            guard.check_database_url(dsn)
            escaped.append(f"dsn:{label}")
        except guard.LabsRefused:
            pass
    for label, env in adversarial.REFUSED_ENVIRONMENTS.items():
        try:
            guard.check_environment(env)
            escaped.append(f"env:{label}")
        except guard.LabsRefused:
            pass
    return escaped


def test_the_real_guard_refuses_the_whole_battery():
    from labs import guard

    assert _survivors(guard) == []


@pytest.mark.parametrize("mutant", sorted(GUARD_MUTANTS))
def test_every_guard_mutant_is_killed(mutant):
    source = (LABS / "guard.py").read_text(encoding="utf-8")
    old, new = GUARD_MUTANTS[mutant]
    assert source.count(old) == 1, f"mutation anchor for {mutant!r} not found: update the mutant"
    mutated = _load(source.replace(old, new), f"labs_guard_mutant_{abs(hash(mutant))}")
    assert _survivors(mutated), f"mutant {mutant!r} survived: no adversarial case covers that protection"


NET_MUTANTS = {
    "any host is local": ("    try:\n        return ipaddress.ip_address(host.split(\"%\", 1)[0]).is_loopback", "    return True\n    try:\n        return ipaddress.ip_address(host.split(\"%\", 1)[0]).is_loopback"),
    "address check disabled": ("    if not _local(host):\n        raise NetworkBlocked(f\"Labs blocks outbound network to", "    if False:\n        raise NetworkBlocked(f\"Labs blocks outbound network to"),
}


@pytest.mark.parametrize("mutant", sorted(NET_MUTANTS))
def test_every_network_guard_mutant_is_killed(mutant):
    source = (LABS / "netguard.py").read_text(encoding="utf-8")
    old, new = NET_MUTANTS[mutant]
    assert source.count(old) == 1, f"mutation anchor for {mutant!r} not found"
    mutated = _load(source.replace(old, new), f"labs_net_mutant_{abs(hash(mutant))}")
    escaped = []
    for host in ("203.0.113.10", "example.com", "db.abcdefghijkl.supabase.co", "10.0.0.1"):
        try:
            mutated._check_address((host, 443))
            escaped.append(host)
        except mutated.NetworkBlocked:
            pass
    assert escaped, f"network mutant {mutant!r} survived"
