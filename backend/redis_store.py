"""shared redis client. unset REDIS_URL → returns None and callers fall back to in-memory."""
import logging

import redis

from backend.config import REDIS_URL

log = logging.getLogger(__name__)

_client: redis.Redis | None = None


def client() -> redis.Redis | None:
    global _client
    if not REDIS_URL:
        return None
    if _client is None:
        _client = redis.Redis.from_url(REDIS_URL, decode_responses=True, socket_timeout=2)
        log.info("redis connected url=%s", REDIS_URL)
    return _client


def reset() -> None:
    """test helper. drops the cached client so the next call() rebuilds it."""
    global _client
    _client = None
