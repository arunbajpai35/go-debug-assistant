"""per-ip sliding-window rate limiter.

two implementations:
  - SlidingWindow (in-memory)         single-replica only. fine for dev / one-pod deploys.
  - RedisSlidingWindow                multi-replica safe; uses sorted sets (ZADD/ZREMRANGEBYSCORE/ZCARD).

`make_limiter(limit, window)` picks one based on REDIS_URL."""
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Protocol

from redis import Redis

from backend.redis_store import client as redis_client


class Limiter(Protocol):
    limit: int

    def check(self, key: str, now: float | None = ...) -> tuple[bool, float]: ...

    def reset(self) -> None: ...


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
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


class RedisSlidingWindow:
    """redis-backed sliding-window limiter using a sorted set per key.
    members are unique tokens; scores are millisecond timestamps."""

    def __init__(self, client: Redis, limit: int, window_seconds: float = 60.0, prefix: str = "rl") -> None:
        self._r = client
        self.limit = limit
        self.window = window_seconds
        self._prefix = prefix

    def _zkey(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    def check(self, key: str, now: float | None = None) -> tuple[bool, float]:
        now_ms = int((now if now is not None else time.time()) * 1000)
        cutoff_ms = now_ms - int(self.window * 1000)
        zkey = self._zkey(key)

        pipe = self._r.pipeline()
        pipe.zremrangebyscore(zkey, 0, cutoff_ms)
        pipe.zcard(zkey)
        _, count = pipe.execute()

        if int(count) >= self.limit:
            oldest_pair = self._r.zrange(zkey, 0, 0, withscores=True)
            retry_s = 0.0
            if oldest_pair and isinstance(oldest_pair, list) and oldest_pair:
                oldest_ms = int(oldest_pair[0][1])
                retry_s = max((oldest_ms + int(self.window * 1000) - now_ms) / 1000.0, 0.0)
            return False, retry_s

        member = uuid.uuid4().hex
        pipe = self._r.pipeline()
        pipe.zadd(zkey, {member: now_ms})
        pipe.expire(zkey, int(self.window) + 1)
        pipe.execute()
        return True, 0.0

    def reset(self) -> None:
        for k in self._r.scan_iter(match=f"{self._prefix}:*"):
            self._r.delete(k)


def make_limiter(limit: int, window_seconds: float = 60.0) -> Limiter:
    r = redis_client()
    if r is not None:
        return RedisSlidingWindow(r, limit, window_seconds)
    return SlidingWindow(limit, window_seconds)
