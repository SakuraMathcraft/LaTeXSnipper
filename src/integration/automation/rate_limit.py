"""Small in-memory fixed-window rate limiter for remote API principals."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque


class RateLimiter:
    def __init__(self, *, clock=time.monotonic, max_keys: int = 1024) -> None:
        self._clock = clock
        self._max_keys = max(1, int(max_keys))
        self._lock = threading.Lock()
        self._events: OrderedDict[tuple[str, ...], deque[float]] = OrderedDict()

    def allow(self, key: tuple[str, ...], limit: int, *, period: float = 60.0) -> bool:
        now = self._clock()
        cutoff = now - period
        with self._lock:
            for stale_key, stale_events in tuple(self._events.items()):
                while stale_events and stale_events[0] <= cutoff:
                    stale_events.popleft()
                if not stale_events:
                    self._events.pop(stale_key, None)
            events = self._events.setdefault(key, deque())
            self._events.move_to_end(key)
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return False
            events.append(now)
            while len(self._events) > self._max_keys:
                self._events.popitem(last=False)
            return True
