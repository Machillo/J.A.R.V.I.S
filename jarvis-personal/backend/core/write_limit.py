"""SEC-12: a technical limit on how fast one account can write (V1-14: no plan limits, only
reasonable technical controls).

Every authenticated POST/PUT/PATCH/DELETE of a Users account counts against a sliding window per
account. Past the limit the request is answered 429 with Retry-After before any work is done, so a
runaway client or a scripted abuse cannot flood the financial tables. The limit is far above what a
person does by hand (bulk paths, such as confirming several mail candidates, are one request each,
well inside it). It is not a plan feature: Free, Basic and VIP share it.

Out of scope on purpose:
- The Owner: not a commercial user, and its automation is not throttled here.
- Deleting the account (`DELETE /auth/me`): always reachable.
- Reads: they cannot change financial truth and the apps retry them on their own.

The window lives in this process's memory: with several instances each one counts its own share,
which still bounds the rate per instance. Nothing about the account is logged.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Callable

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
WRITES_PER_WINDOW = 120
WINDOW_SECONDS = 60.0
# Bounded memory: the accounts seen least recently are forgotten first.
MAX_TRACKED_ACCOUNTS = 10_000
ALWAYS_ALLOWED = frozenset({("DELETE", "/auth/me")})


class WriteLimiter:
    def __init__(self, limit: int = WRITES_PER_WINDOW, window: float = WINDOW_SECONDS,
                 max_accounts: int = MAX_TRACKED_ACCOUNTS, clock: Callable[[], float] = time.monotonic):
        self.limit, self.window, self.max_accounts, self.clock = limit, window, max_accounts, clock
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def check(self, account_id: str) -> float | None:
        """Records one write for the account. None = allowed; otherwise the seconds to wait."""
        now = self.clock()
        with self._lock:
            hits = self._hits.pop(account_id, None) or deque()
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            self._hits[account_id] = hits
            while len(self._hits) > self.max_accounts:
                self._hits.popitem(last=False)
            if len(hits) >= self.limit:
                return max(hits[0] + self.window - now, 1.0)
            hits.append(now)
            return None

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = WriteLimiter()


def retry_after_for(user: dict, method: str, path: str) -> float | None:
    """The seconds this write must wait, or None when it may run (or is outside the limit)."""
    if method not in WRITE_METHODS or (method, path) in ALWAYS_ALLOWED:
        return None
    if user.get("role") == "owner":
        return None
    account_id = str(user.get("account_id") or "")
    if not account_id:
        return None
    return limiter.check(account_id)
