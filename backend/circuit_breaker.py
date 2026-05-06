"""three-state circuit breaker for the llm call.

states:
  CLOSED     normal. all calls go through. consecutive failures count up.
  OPEN       calls refused immediately for `cooldown_seconds`. the count is frozen.
  HALF_OPEN  one trial allowed. success → CLOSED. failure → OPEN again with timer reset.

failure threshold + cooldown are env-driven. counters reset on any successful call.

this is a single-process, thread-safe breaker. for multi-replica setups, share state via
redis — documented honestly, deliberately not done in v1."""
import logging
import threading
import time
from enum import StrEnum

log = logging.getLogger(__name__)


class State(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpen(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: float, name: str = "llm") -> None:
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown_seconds
        self.name = name
        self._state = State.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        with self._lock:
            return self._state

    def _maybe_half_open(self, now: float) -> None:
        if (
            self._state is State.OPEN
            and self._opened_at is not None
            and now - self._opened_at >= self.cooldown
        ):
            log.info("circuit %s -> half_open after cooldown", self.name)
            self._state = State.HALF_OPEN

    def before_call(self, now: float | None = None) -> None:
        """raise CircuitOpen if calls are not allowed right now."""
        t = now if now is not None else time.monotonic()
        with self._lock:
            self._maybe_half_open(t)
            if self._state is State.OPEN:
                raise CircuitOpen(f"circuit {self.name} is open; cooldown {self.cooldown}s")
            # CLOSED or HALF_OPEN both allow exactly one call

    def on_success(self) -> None:
        with self._lock:
            if self._state is not State.CLOSED:
                log.info("circuit %s -> closed (success)", self.name)
            self._state = State.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None

    def on_failure(self, now: float | None = None) -> None:
        t = now if now is not None else time.monotonic()
        with self._lock:
            self._consecutive_failures += 1
            if self._state is State.HALF_OPEN:
                log.warning("circuit %s -> open (half_open trial failed)", self.name)
                self._state = State.OPEN
                self._opened_at = t
                return
            if self._consecutive_failures >= self.failure_threshold:
                log.warning(
                    "circuit %s -> open after %d consecutive failures",
                    self.name,
                    self._consecutive_failures,
                )
                self._state = State.OPEN
                self._opened_at = t

    def reset(self) -> None:
        with self._lock:
            self._state = State.CLOSED
            self._consecutive_failures = 0
            self._opened_at = None
