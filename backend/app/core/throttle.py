"""In-memory throttle for failed sign-in attempts.

This is deliberately small and per-process: it blunts online password guessing
against a single API task, where the work is dominated by Argon2 anyway. It is
**not** a substitute for a real rate limit at the edge (ALB/WAF), which is still
the right place to stop volumetric attacks.

Keyed by account and by caller, so one noisy client cannot lock out everyone
and one account cannot be brute-forced from one address.
"""

from __future__ import annotations

import time
from collections import deque
from functools import lru_cache
from threading import Lock

#: Attempts allowed per window before the caller is asked to slow down.
ACCOUNT_LIMIT = 10
CALLER_LIMIT = 30
WINDOW_SECONDS = 60.0


class AttemptThrottle:
    """A sliding window of failed attempts per key."""

    def __init__(self, *, limit: int, window_seconds: float = WINDOW_SECONDS) -> None:
        self._limit = limit
        self._window = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def retry_after(self, key: str) -> float | None:
        """Seconds to wait when `key` is over budget, otherwise None."""
        with self._lock:
            recent = self._live(key)
            if len(recent) < self._limit:
                return None
            return max(0.0, self._window - (time.monotonic() - recent[0]))

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._live(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def clear(self) -> None:
        """Forget everything (used between tests)."""
        with self._lock:
            self._attempts.clear()

    def _live(self, key: str) -> deque[float]:
        """Drop attempts that fell outside the window; assumes the lock is held."""
        cutoff = time.monotonic() - self._window
        attempts = self._attempts.setdefault(key, deque())
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts


@lru_cache
def get_account_throttle() -> AttemptThrottle:
    return AttemptThrottle(limit=ACCOUNT_LIMIT)


@lru_cache
def get_caller_throttle() -> AttemptThrottle:
    return AttemptThrottle(limit=CALLER_LIMIT)
