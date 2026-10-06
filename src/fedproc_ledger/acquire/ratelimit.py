"""Token bucket with an injectable clock so it can be tested without sleeping."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class TokenBucket:
    def __init__(
        self,
        rate_per_s: float,
        capacity: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_s <= 0:
            raise ValueError("rate_per_s must be positive")
        self.rate = rate_per_s
        self.capacity = capacity if capacity is not None else max(1.0, rate_per_s)
        self._clock, self._sleep = clock, sleep
        self._tokens = self.capacity
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
        self._last = now

    def acquire(self, n: float = 1.0) -> float:
        """Block until n tokens are available; returns the seconds waited. Thread-safe."""
        with self._lock:
            self._refill()
            waited = 0.0
            if self._tokens < n:
                waited = (n - self._tokens) / self.rate
                self._sleep(waited)
                self._refill()
            self._tokens -= n
            return waited
