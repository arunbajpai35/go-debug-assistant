"""daily llm spend cap.

tracks estimated usd cost from openai chat completions and refuses further calls once a daily
budget is exhausted. resets at utc midnight.

cost is *estimated* from prompt+completion token counts using a static price table. real billing
runs on azure's invoice; this is a guard rail, not an invoice.

two implementations:
  - DailyBudget        in-memory. single-replica only.
  - RedisDailyBudget   multi-replica safe; INCRBYFLOAT on a per-day key with a 48h expiry.

`make_budget(limit)` picks one based on REDIS_URL."""
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol, cast

from redis import Redis

from backend.config import LLM_DAILY_BUDGET_USD
from backend.redis_store import client as redis_client

log = logging.getLogger(__name__)


# usd per 1k tokens.
PRICES_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.00250, 0.01000),
    "gpt-4.1-mini": (0.00040, 0.00160),
    "gpt-4.1": (0.00200, 0.00800),
    "gpt-4": (0.03000, 0.06000),
    "gpt-35-turbo": (0.00050, 0.00150),
}
FALLBACK_PRICE = (0.00250, 0.01000)


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = PRICES_PER_1K.get(model, FALLBACK_PRICE)
    return (prompt_tokens / 1000.0) * in_price + (completion_tokens / 1000.0) * out_price


class BudgetExceeded(RuntimeError):
    pass


class Budget(Protocol):
    limit: float

    @property
    def spent_usd(self) -> float: ...

    def check(self, now: datetime | None = ...) -> None: ...

    def record(self, model: str, prompt_tokens: int, completion_tokens: int, now: datetime | None = ...) -> float: ...


@dataclass
class _State:
    day: date
    spent_usd: float = 0.0


class DailyBudget:
    def __init__(self, daily_limit_usd: float) -> None:
        self.limit = daily_limit_usd
        self._state = _State(day=datetime.now(UTC).date())
        self._lock = threading.Lock()

    def _roll_if_new_day(self, now: datetime) -> None:
        today = now.date()
        if today != self._state.day:
            log.info(
                "budget rolled over",
                extra={"prev_day": self._state.day.isoformat(), "prev_spent_usd": self._state.spent_usd},
            )
            self._state = _State(day=today)

    def check(self, now: datetime | None = None) -> None:
        t = now or datetime.now(UTC)
        with self._lock:
            self._roll_if_new_day(t)
            if self._state.spent_usd >= self.limit:
                raise BudgetExceeded(
                    f"daily llm budget exhausted: spent ${self._state.spent_usd:.4f} >= limit ${self.limit:.2f}"
                )

    def record(self, model: str, prompt_tokens: int, completion_tokens: int, now: datetime | None = None) -> float:
        cost = cost_for(model, prompt_tokens, completion_tokens)
        t = now or datetime.now(UTC)
        with self._lock:
            self._roll_if_new_day(t)
            self._state.spent_usd += cost
            return self._state.spent_usd

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._state.spent_usd


class RedisDailyBudget:
    """one floating-point counter per utc day. INCRBYFLOAT + EXPIRE 48h so old days expire on
    their own. all replicas read/write the same key, so spend is correctly aggregated."""

    def __init__(self, client: Redis, daily_limit_usd: float, prefix: str = "budget") -> None:
        self._r = client
        self.limit = daily_limit_usd
        self._prefix = prefix

    def _key(self, now: datetime) -> str:
        return f"{self._prefix}:{now.date().isoformat()}"

    def check(self, now: datetime | None = None) -> None:
        t = now or datetime.now(UTC)
        raw = cast(str | None, self._r.get(self._key(t)))
        spent = float(raw) if raw is not None else 0.0
        if spent >= self.limit:
            raise BudgetExceeded(
                f"daily llm budget exhausted: spent ${spent:.4f} >= limit ${self.limit:.2f}"
            )

    def record(self, model: str, prompt_tokens: int, completion_tokens: int, now: datetime | None = None) -> float:
        cost = cost_for(model, prompt_tokens, completion_tokens)
        t = now or datetime.now(UTC)
        key = self._key(t)
        pipe = self._r.pipeline()
        pipe.incrbyfloat(key, cost)
        pipe.expire(key, 48 * 3600)
        new_total, _ = pipe.execute()
        return float(new_total)

    @property
    def spent_usd(self) -> float:
        raw = cast(str | None, self._r.get(self._key(datetime.now(UTC))))
        return float(raw) if raw is not None else 0.0


def make_budget(daily_limit_usd: float) -> Budget:
    r = redis_client()
    if r is not None:
        log.info("budget: redis-backed")
        return RedisDailyBudget(r, daily_limit_usd)
    log.info("budget: in-memory (single-replica)")
    return DailyBudget(daily_limit_usd)


# module-level singleton wired in llm.py
budget: Budget = make_budget(LLM_DAILY_BUDGET_USD)
