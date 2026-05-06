"""per-ip sliding-window rate limiter.

in-memory only. fine for a single replica, useless behind multiple instances — replace with a
redis-backed limiter (or slowapi) before scaling out. documented loud here so the next reader
isn't surprised."""
import threading
import time
from collections import defaultdict, deque


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        """returns (allowed, retry_after_seconds). retry_after is 0 when allowed."""
        t = now if now is not None else time.monotonic()
        cutoff = t - self.window
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.limit:
                retry = self.window - (t - q[0])
                return False, max(retry, 0.0)
            q.append(t)
            return True, 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
