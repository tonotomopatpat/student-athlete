"""In-process sliding-window limits per key (single app process; see the deployment notes for scaling)."""

import threading
import time
from collections import defaultdict, deque

from app.core.errors import ApiError

_registry: list["SlidingWindowLimiter"] = []


class SlidingWindowLimiter:
    def __init__(self, name: str, limit: int, window_seconds: float, message: str) -> None:
        self.name = name
        self.limit = limit
        self.window = window_seconds
        self.message = message
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        _registry.append(self)

    def hit(self, key: str | int) -> None:
        """Record one use for `key`, raising 429 when the window is full."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[str(key)]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                raise ApiError(429, "rate_limited", self.message)
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def reset_all() -> None:
    for limiter in _registry:
        limiter.reset()


upload_limiter = SlidingWindowLimiter("uploads", 40, 3600, "Upload limit reached. Try again in an hour.")
syllabus_limiter = SlidingWindowLimiter("syllabus", 20, 3600, "Too many syllabus uploads. Try again in an hour.")
extract_limiter = SlidingWindowLimiter("extract", 30, 3600, "Too many re-reads. Try again in an hour.")
