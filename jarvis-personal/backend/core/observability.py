"""Server-side production signals: structured logs, deduplicated alerts, recovery.

One entry point, ``report()``, for anything the backend itself notices (an
unhandled 5xx, the database unreachable, a provider failing, a job failing). It

1. writes one JSON log line (``dincr.ops`` logger) with sanitized fields only;
2. groups identical problems by fingerprint (component, event, route, exact
   status, error class/code) in ``AlertGate``: the first occurrence alerts, later
   ones only count until the cooldown ends (then one summary "N occurrences in
   M min"), a global budget caps alerts per window, a higher severity alerts at
   once, and a quiet period sends one RECOVERED;
3. hands the few alerts that pass to a bounded background queue that posts to
   the existing Discord support channel (same webhook validation, no mentions
   except the configured role on CRITICAL).

Client-reported incidents (``/product-ops/incidents``) keep their own pipeline in
product_ops/service.py; this module covers what only the server can see,
including the case where no client can reach the API.

Privacy: callers pass categories and codes, never payloads. Every string still
goes through ``sanitize_text`` (tokens, secrets, emails, long numbers, URLs'
query strings, control characters and Discord mentions are removed). State is
process-local on purpose: it keeps working when the database is down; with N
processes an incident can alert up to N times per cooldown.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("dincr.ops")

SEVERITIES = ("info", "warning", "error", "critical")
_RANK = {name: index for index, name in enumerate(SEVERITIES)}

# --- Sanitization ---------------------------------------------------------------

_SECRET_KEYS = (
    r"access[_-]?token|refresh[_-]?token|id[_-]?token|token|secret|password|passwd|pwd|"
    r"authorization|api[_-]?key|apikey|client[_-]?secret|code[_-]?verifier|code|cookie|"
    r"session|signature|sig|key|jwt|receipt|purchase[_-]?token|dsn"
)
_REDACTIONS = (
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [redacted]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}(?:\.[A-Za-z0-9_-]*)?"), "[jwt]"),
    (re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@"), "[credentials]@"),
    (re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{6,}"), "Basic [redacted]"),
    (re.compile(rf"(?i)(?<![A-Za-z0-9])([A-Za-z0-9]*[_-]?(?:{_SECRET_KEYS}))[\"']?(\s*[=:]\s*[\"']?)[^\s&,;\"']+"), r"\1\2[redacted]"),
    (re.compile(r"(?i)(https?://[^\s?#]+)[?#][^\s]*"), r"\1"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
    (re.compile(r"\b(?:sk|pk|rk|ghp|gho|github_pat|xox[abpr]|AKIA|AIza)[A-Za-z0-9_-]{8,}"), "[secret]"),
    (re.compile(r"\b[A-Za-z0-9_-]{40,}\b"), "[redacted]"),
    (re.compile(r"\d[\d ,.-]{4,}\d"), "[number]"),
)


def sanitize_text(value: Any, limit: int = 160) -> str:
    """A string that can go to logs and Discord: no secrets, PII, numbers or markup."""
    text = str(value if value is not None else "")
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    # Discord: no code-fence escape, no @everyone/@here/user or role mentions.
    text = text.replace("`", "'").replace("@", "(at)")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def normalize_route(path: Any) -> str:
    """A route label without ids or query: /user-product/free/movements/:id."""
    route = str(path or "/unknown").split("?", 1)[0].split("#", 1)[0]
    route = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27,}", ":id", route, flags=re.I)
    route = re.sub(r"/[a-z_]+:\d+(?=/|$)", "/:id", route)
    route = re.sub(r"/\d+(?=/|$)", "/:id", route)
    route = re.sub(r"[^A-Za-z0-9/_:{}.-]", "", route)
    return route[:120] or "/unknown"


def environment() -> str:
    explicit = os.getenv("DINCR_ENVIRONMENT", "").strip()
    if explicit:
        return sanitize_text(explicit, 20)
    return "render" if os.getenv("RENDER") else "local"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# --- Signals --------------------------------------------------------------------

@dataclass
class Signal:
    component: str
    event: str
    severity: str
    route: str | None = None
    method: str | None = None
    status: int | None = None
    error_class: str | None = None
    error_code: str | None = None
    duration_ms: int | None = None
    request_id: str | None = None

    def clean(self) -> "Signal":
        return Signal(
            component=sanitize_text(self.component, 40) or "backend",
            event=sanitize_text(self.event, 60) or "event",
            severity=self.severity if self.severity in _RANK else "error",
            route=normalize_route(self.route) if self.route else None,
            method=sanitize_text(self.method, 8).upper() if self.method else None,
            status=int(self.status) if isinstance(self.status, int) and 100 <= self.status <= 599 else None,
            error_class=sanitize_text(self.error_class, 60) if self.error_class else None,
            error_code=sanitize_text(self.error_code, 40) if self.error_code else None,
            duration_ms=max(0, int(self.duration_ms)) if isinstance(self.duration_ms, (int, float)) else None,
            request_id=self.request_id if self.request_id and re.fullmatch(r"[A-Za-z0-9_-]{8,80}", self.request_id) else None,
        )

    def fingerprint(self) -> str:
        # Exact status: a 502 (provider down) and a 500 (DINCR bug) are different problems.
        parts = (self.component, self.event, self.route or "-", str(self.status or "-"), self.error_class or "-", self.error_code or "-")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


@dataclass
class _Incident:
    signal: Signal
    first_seen: float
    last_seen: float
    total: int = 0
    since_alert: int = 0
    alerted_at: float | None = None
    alerted_severity: str | None = None


@dataclass
class Alert:
    kind: str  # "new" | "ongoing" | "escalated" | "recovered" | "storm"
    signal: Signal
    fingerprint: str
    count: int
    first_seen: float
    last_seen: float
    window_seconds: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class AlertGate:
    """Deduplication, cooldown, global budget, escalation and recovery (thread-safe)."""

    def __init__(self, *, cooldown_seconds: float = 600, quiet_seconds: float = 900,
                 budget: int = 12, budget_window_seconds: float = 600, max_tracked: int = 500,
                 clock: Callable[[], float] = time.monotonic):
        self.cooldown, self.quiet, self.budget, self.budget_window = cooldown_seconds, quiet_seconds, budget, budget_window_seconds
        self.max_tracked, self.clock = max_tracked, clock
        self._lock = threading.Lock()
        self._incidents: dict[str, _Incident] = {}
        self._sent: list[float] = []
        self._storm_suppressed = 0
        self._storm_reported_at: float | None = None

    def _budget_ok(self, now: float) -> bool:
        self._sent = [t for t in self._sent if now - t < self.budget_window]
        return len(self._sent) < self.budget

    def _emit(self, now: float, alerts: list[Alert], alert: Alert) -> None:
        if self._budget_ok(now):
            self._sent.append(now)
            alerts.append(alert)
            return
        self._storm_suppressed += 1
        # Budget exhausted: one notice per window (outside the budget) says alerts are
        # being dropped; everything stays in the dincr.ops logs and the Owner view.
        if self._storm_reported_at is None or now - self._storm_reported_at >= self.budget_window:
            self._storm_reported_at = now
            signal = Signal("observability", "alert_budget_exceeded", "critical")
            alerts.append(Alert("storm", signal, signal.fingerprint(), self.budget, now, now, int(self.budget_window)))

    def record(self, signal: Signal, *, alert_min: str = "error") -> list[Alert]:
        """Count one occurrence; return the alerts to send now (usually none)."""
        now, alerts = self.clock(), []
        fingerprint = signal.fingerprint()
        with self._lock:
            alerts.extend(self._sweep(now))
            incident = self._incidents.get(fingerprint)
            if incident is None:
                if len(self._incidents) >= self.max_tracked:
                    oldest = min(self._incidents, key=lambda key: self._incidents[key].last_seen)
                    self._incidents.pop(oldest)
                incident = self._incidents[fingerprint] = _Incident(signal, now, now)
            incident.total += 1
            incident.since_alert += 1
            incident.last_seen = now
            if _RANK[signal.severity] >= _RANK[incident.signal.severity]:
                incident.signal = signal  # latest occurrence (its request ID), highest severity
            if _RANK[incident.signal.severity] < _RANK[alert_min]:
                return alerts
            kind = None
            if incident.alerted_at is None:
                kind = "new"
            elif incident.alerted_severity and _RANK[incident.signal.severity] > _RANK[incident.alerted_severity]:
                kind = "escalated"
            elif now - incident.alerted_at >= self.cooldown:
                kind = "ongoing"
            if kind:
                before = len(alerts)
                self._emit(now, alerts, Alert(kind, incident.signal, fingerprint, incident.since_alert, incident.first_seen,
                                              now, int(now - (incident.alerted_at or incident.first_seen))))
                if len(alerts) > before:
                    incident.alerted_at, incident.alerted_severity, incident.since_alert = now, incident.signal.severity, 0
        return alerts

    def resolve(self, component: str, event: str | None = None) -> list[Alert]:
        """An explicit recovery (a probe succeeded): RECOVERED for alerted incidents."""
        now, alerts = self.clock(), []
        with self._lock:
            for key, incident in list(self._incidents.items()):
                if incident.signal.component == component and (event is None or incident.signal.event == event):
                    self._incidents.pop(key)
                    if incident.alerted_at is not None:
                        self._emit(now, alerts, Alert("recovered", incident.signal, key, incident.total, incident.first_seen, incident.last_seen))
        return alerts

    def sweep(self) -> list[Alert]:
        with self._lock:
            return self._sweep(self.clock())

    def _sweep(self, now: float) -> list[Alert]:
        alerts: list[Alert] = []
        for key, incident in list(self._incidents.items()):
            if now - incident.last_seen >= self.quiet:
                self._incidents.pop(key)
                if incident.alerted_at is not None:
                    self._emit(now, alerts, Alert("recovered", incident.signal, key, incident.total, incident.first_seen,
                                                  incident.last_seen, extra={"quiet_minutes": int(self.quiet // 60)}))
        return alerts

    def snapshot(self) -> list[dict[str, Any]]:
        now = self.clock()
        with self._lock:
            rows = sorted(({
                "fingerprint": key, "component": i.signal.component, "event": i.signal.event, "severity": i.signal.severity,
                "route": i.signal.route, "status": i.signal.status, "error_class": i.signal.error_class,
                "occurrences": i.total, "first_seen_seconds_ago": int(now - i.first_seen),
                "last_seen_seconds_ago": int(now - i.last_seen), "alerted": i.alerted_at is not None,
            } for key, i in self._incidents.items()), key=lambda row: row["last_seen_seconds_ago"])
            return rows


class SpikeCounter:
    """Sliding-window count of one kind of event (e.g. 5xx) for spike detection.

    Keeps at most ``cap`` timestamps: past the threshold the exact number no longer
    matters, and a flood must not grow memory or CPU.
    """

    def __init__(self, window_seconds: float = 300, clock: Callable[[], float] = time.monotonic, cap: int = 1000):
        from collections import deque

        self.window, self.clock, self._lock = window_seconds, clock, threading.Lock()
        self._times = deque(maxlen=cap)

    def add(self) -> int:
        now = self.clock()
        with self._lock:
            while self._times and now - self._times[0] >= self.window:
                self._times.popleft()
            self._times.append(now)
            return len(self._times)


# --- Delivery -------------------------------------------------------------------

def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def alerts_enabled() -> bool:
    return os.getenv("OPS_ALERTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def alert_min_severity() -> str:
    value = os.getenv("OPS_ALERT_MIN_SEVERITY", "error").strip().lower()
    return value if value in _RANK else "error"


def _webhook() -> str:
    return (os.getenv("OPS_DISCORD_WEBHOOK_URL", "") or os.getenv("SUPPORT_DISCORD_WEBHOOK_URL", "")).strip()


def _ago(seconds: float) -> str:
    return f"{int(seconds // 60)} min" if seconds >= 60 else f"{int(seconds)} s"


def format_alert(alert: Alert, now: float | None = None) -> str:
    """Compact Discord text; every value is already sanitized by Signal.clean()."""
    now = time.monotonic() if now is None else now
    s = alert.signal
    title = {
        "new": s.severity.upper(), "ongoing": f"{s.severity.upper()} · CONTINÚA", "escalated": f"{s.severity.upper()} · ESCALÓ",
        "recovered": "RECOVERED", "storm": "CRITICAL · DEMASIADAS ALERTAS",
    }[alert.kind]
    lines = [f"Entorno: {environment()}", f"Componente: {s.component}", f"Evento: {s.event}"]
    if s.route:
        lines.append(f"Ruta: {s.method + ' ' if s.method else ''}{s.route}")
    if s.status:
        lines.append(f"HTTP: {s.status}")
    if s.error_class or s.error_code:
        lines.append(f"Error: {' '.join(filter(None, (s.error_class, s.error_code)))}")
    if s.duration_ms is not None:
        lines.append(f"Latencia: {s.duration_ms} ms")
    if alert.kind == "storm":
        lines.append(f"Se enviaron {alert.count} alertas en {_ago(alert.window_seconds)}; las nuevas se suprimen hasta que pase la ventana.")
        lines.append("Todo sigue en los logs dincr.ops y en /product-ops/owner/observability.")
    elif alert.kind == "recovered":
        lines.append(f"Ocurrencias totales: {alert.count}; última hace {_ago(now - alert.last_seen)}")
    else:
        lines.append(f"Ocurrencias: {alert.count}" + (f" en {_ago(alert.window_seconds)}" if alert.kind != "new" else ""))
        lines.append(f"Primera vez: hace {_ago(now - alert.first_seen)}")
    if s.request_id:
        lines.append(f"Request ID: {s.request_id}")
    lines.append(f"Huella: {alert.fingerprint} · {utc_now().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    return f"**DINCR OPS · {title}**\n```\n" + "\n".join(lines) + "\n```"


class _Dispatcher:
    """One daemon thread, bounded queue: alerting can never block or flood requests."""

    def __init__(self, maxsize: int = 50):
        self._queue: queue.Queue = queue.Queue(maxsize=maxsize)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.dropped = 0
        self.sender: Callable[[str, bool], bool] = _post_discord

    def submit(self, text: str, critical: bool) -> bool:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, name="dincr-ops-alerts", daemon=True)
                self._thread.start()
        try:
            self._queue.put_nowait((text, critical))
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def _run(self) -> None:
        while True:
            text, critical = self._queue.get()
            try:
                self.sender(text, critical)
            except Exception as exc:  # never let the alert thread die
                logger.error("ops alert delivery crashed error=%s", type(exc).__name__)


def _post_discord(text: str, critical: bool) -> bool:
    import requests
    from backend.product_ops.service import _discord_webhook_host

    webhook = _webhook()
    host = _discord_webhook_host(webhook) if webhook else None
    if not host:
        logger.warning("ops alert not delivered: no valid Discord webhook configured")
        return False
    role_id = os.getenv("SUPPORT_DISCORD_ALERT_ROLE_ID", "").strip()
    role_id = role_id if critical and re.fullmatch(r"\d{5,30}", role_id) else ""
    try:
        response = requests.post(webhook, json={
            "content": (f"<@&{role_id}> " if role_id else "") + text[:1900],
            "allowed_mentions": {"parse": [], "roles": [role_id]} if role_id else {"parse": []},
        }, timeout=5)
        if response.status_code in {200, 204}:
            return True
        logger.error("ops alert delivery failed host=%s status=%s", host, response.status_code)
    except Exception as exc:
        # Type only: a connection error message carries the webhook URL (its secret).
        logger.error("ops alert delivery failed host=%s error=%s", host, type(exc).__name__)
    return False


GATE = AlertGate(
    cooldown_seconds=_int_env("OPS_ALERT_COOLDOWN_SECONDS", 600),
    quiet_seconds=_int_env("OPS_ALERT_RECOVERY_SECONDS", 900),
    budget=_int_env("OPS_ALERT_BUDGET", 12),
    budget_window_seconds=_int_env("OPS_ALERT_BUDGET_WINDOW_SECONDS", 600),
)
DISPATCHER = _Dispatcher()
SERVER_ERRORS = SpikeCounter(window_seconds=300)
SPIKE_THRESHOLD = _int_env("OPS_5XX_SPIKE_THRESHOLD", 20)
_HEARTBEATS: dict[str, dict[str, Any]] = {}
_HEARTBEAT_LOCK = threading.Lock()


def _deliver(alerts: list[Alert]) -> None:
    for alert in alerts:
        logger.warning(json.dumps({"event": "ops_alert", "kind": alert.kind, "fingerprint": alert.fingerprint,
                                   "component": alert.signal.component, "alert_event": alert.signal.event,
                                   "severity": alert.signal.severity, "count": alert.count}, sort_keys=True))
        if alerts_enabled():
            DISPATCHER.submit(format_alert(alert), alert.kind != "recovered" and alert.signal.severity == "critical")


def log_signal(signal: Signal, level: int | None = None) -> None:
    record = {"ts": utc_now().isoformat(timespec="milliseconds"), "env": environment(), "service": "dincr-backend",
              **{key: value for key, value in signal.__dict__.items() if value is not None}}
    level = level if level is not None else {"info": logging.INFO, "warning": logging.WARNING}.get(signal.severity, logging.ERROR)
    logger.log(level, json.dumps(record, sort_keys=True, default=str))


_ESCALATIONS: dict[str, SpikeCounter] = {}


def report(component: str, event: str, severity: str = "error", *, escalate_after: int | None = None, **fields: Any) -> None:
    """Log and (deduplicated) alert one server-side problem. Never raises.

    ``escalate_after``: a problem that is expected now and then for one user (a
    provider hiccup, a slow request) is raised one severity level once it happens
    this many times in 10 minutes across the process.
    """
    try:
        if escalate_after:
            key = f"{component}|{event}|{normalize_route(fields.get('route')) if fields.get('route') else '-'}"
            if key not in _ESCALATIONS and len(_ESCALATIONS) >= 500:
                _ESCALATIONS.clear()  # bounded: a flood of distinct routes resets the counters
            counter = _ESCALATIONS.setdefault(key, SpikeCounter(window_seconds=600, cap=100))
            if counter.add() >= escalate_after and severity in _RANK and severity != "critical":
                severity = SEVERITIES[_RANK[severity] + 1]
        signal = Signal(component, event, severity, **fields).clean()
        log_signal(signal)
        _deliver(GATE.record(signal, alert_min=alert_min_severity()))
        # Deliberate 5xx (warnings: feature paused, store off, secret unset) never count:
        # anyone can trigger them anonymously, so they must not page the Owner.
        if (signal.status and signal.status >= 500 and _RANK[signal.severity] >= _RANK["error"]
                and SERVER_ERRORS.add() >= SPIKE_THRESHOLD):
            spike = Signal("api", "5xx_spike", "critical", error_code=f">={SPIKE_THRESHOLD}/5min").clean()
            _deliver(GATE.record(spike, alert_min=alert_min_severity()))
    except Exception as exc:
        logger.error("ops report failed error=%s", type(exc).__name__)


def recovered(component: str, event: str | None = None) -> None:
    """A probe or job succeeded again: RECOVERED for its alerted incidents."""
    try:
        _deliver(GATE.resolve(sanitize_text(component, 40), sanitize_text(event, 60) if event else None))
    except Exception as exc:
        logger.error("ops recovery failed error=%s", type(exc).__name__)


def heartbeat(job: str, ok: bool, *, duration_ms: int | None = None, error_class: str | None = None) -> None:
    """Last run of a background job in this process (shown in the Owner health view)."""
    job = sanitize_text(job, 40)
    with _HEARTBEAT_LOCK:
        entry = _HEARTBEATS.setdefault(job, {"runs": 0, "failures": 0})
        entry["runs"] += 1
        entry["last_run_at"] = utc_now().isoformat(timespec="seconds")
        entry["last_ok"] = ok
        entry["last_duration_ms"] = duration_ms
        if ok:
            entry["last_success_at"] = entry["last_run_at"]
        else:
            entry["failures"] += 1
    if ok:
        recovered("job", f"{job}_failed")
    else:
        report("job", f"{job}_failed", "error", error_class=error_class, duration_ms=duration_ms)


def heartbeats() -> dict[str, dict[str, Any]]:
    with _HEARTBEAT_LOCK:
        return {job: dict(entry) for job, entry in _HEARTBEATS.items()}


def sweep() -> None:
    try:
        _deliver(GATE.sweep())
    except Exception as exc:
        logger.error("ops sweep failed error=%s", type(exc).__name__)


def status_snapshot() -> dict[str, Any]:
    return {
        "environment": environment(),
        "alerts_enabled": alerts_enabled(),
        "webhook_configured": bool(_webhook()),
        "alert_min_severity": alert_min_severity(),
        "cooldown_seconds": int(GATE.cooldown), "recovery_seconds": int(GATE.quiet),
        "budget": {"alerts": GATE.budget, "window_seconds": int(GATE.budget_window)},
        "spike_threshold_per_5min": SPIKE_THRESHOLD,
        "dropped_alerts": DISPATCHER.dropped,
        "suppressed_alerts": GATE._storm_suppressed,
        "incidents": GATE.snapshot(),
        "jobs": heartbeats(),
    }


# --- Exceptions, access log, logging setup ------------------------------------------

def exception_summary(exc: BaseException) -> str:
    """One log line that explains an unexpected error without leaking data.

    Keeps exception types, Postgres error codes, schema identifiers (table,
    constraint, column) and code locations. Exception messages are dropped on
    purpose: driver messages can quote row values (emails, amounts, tokens).
    """
    import traceback
    from pathlib import Path

    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen and len(parts) < 3:
        seen.add(id(current))
        info = [type(current).__name__]
        pgcode = getattr(current, "pgcode", None)
        if pgcode:
            info.append(f"pgcode={pgcode}")
        diag = getattr(current, "diag", None)
        for label, attr in (("table", "table_name"), ("constraint", "constraint_name"), ("column", "column_name")):
            value = getattr(diag, attr, None) if diag is not None else None
            if value:
                info.append(f"{label}={value}")
        frames = [frame for frame in traceback.extract_tb(current.__traceback__) if "backend" in frame.filename.replace("\\", "/")]
        if frames:
            info.append("at " + " <- ".join(
                f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}" for frame in reversed(frames[-6:])
            ))
        parts.append(" ".join(info))
        current = current.__cause__ or current.__context__
    return " | caused by ".join(parts)


access_logger = logging.getLogger("dincr.access")
SLOW_REQUEST_MS = _int_env("OPS_SLOW_REQUEST_MS", 5000)
# Long by design: batch syncs and provider round trips answer in their own time.
SLOW_EXEMPT_SUFFIXES = ("/cron", "/sync", "/maintenance", "/push", "/callback", "/snapshot")


def access(route: Any, path: str, method: str, status: int, duration_ms: int, request_id: str | None) -> None:
    """One structured access line per request (route template, never the raw URL)."""
    try:
        template = getattr(route, "path", None) or normalize_route(path)
        signal = Signal("api", "http_request", "info", route=template, method=method, status=status,
                        duration_ms=duration_ms, request_id=request_id).clean()
        record = {"ts": utc_now().isoformat(timespec="milliseconds"), "env": environment(), "service": "dincr-backend",
                  **{key: value for key, value in signal.__dict__.items() if value is not None and key not in {"component", "severity"}}}
        access_logger.info(json.dumps(record, sort_keys=True))
        if duration_ms >= SLOW_REQUEST_MS and not str(template).endswith(SLOW_EXEMPT_SUFFIXES):
            report("api", "slow_request", "warning", route=template, method=method, status=status,
                   duration_ms=duration_ms, request_id=request_id, escalate_after=10)
    except Exception as exc:
        logger.error("access log failed error=%s", type(exc).__name__)


class _StripQueryString(logging.Filter):
    """uvicorn's access log prints the raw path: drop the query (OAuth codes, push tokens)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
            record.args = (*args[:2], args[2].split("?", 1)[0] + "?[redacted]", *args[3:])
        return True


_configured = False


def configure_logging() -> None:
    """Make the DINCR operational loggers visible (INFO, one JSON line each) and redact
    query strings from uvicorn's access log. Other loggers keep their current setup."""
    global _configured
    if _configured:
        return
    _configured = True
    for name in ("dincr.ops", "dincr.access"):
        target = logging.getLogger(name)
        if not target.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
            target.addHandler(handler)
        target.setLevel(logging.INFO)
        target.propagate = False
    logging.getLogger("uvicorn.access").addFilter(_StripQueryString())
