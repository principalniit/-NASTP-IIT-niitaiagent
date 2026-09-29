"""Small in-process sliding-window limiter for failed login attempts.

Limitation: state is per process. Use a shared store before running several API instances.
"""

import time
from collections import defaultdict, deque
from threading import Lock


class FailureLimiter:
    SWEEP_ABOVE = 10_000

    def __init__(self, max_failures: int, window_seconds: int) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        events = self._events[key]
        while events and now - events[0] > self.window:
            events.popleft()
        return events

    def is_blocked(self, *keys: str) -> bool:
        now = time.monotonic()
        with self._lock:
            blocked = False
            for k in keys:
                if k not in self._events:
                    continue
                count = len(self._prune(k, now))
                if count == 0:
                    del self._events[k]  # forget keys whose failures have expired
                blocked = blocked or count >= self.max_failures
            return blocked

    def record_failure(self, *keys: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._events) > self.SWEEP_ABOVE:
                self._sweep(now)
            for k in keys:
                self._prune(k, now).append(now)

    def _sweep(self, now: float) -> None:
        """Drop every key whose failures have all expired, so memory stays bounded."""
        for k in list(self._events):
            if not self._prune(k, now):
                del self._events[k]

    def reset(self, *keys: str) -> None:
        with self._lock:
            for k in keys:
                self._events.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
