"""daily llm spend cap.

tracks estimated usd cost from openai chat completions and refuses further calls once a daily
budget is exhausted. resets at utc midnight.

cost is *estimated* from prompt+completion token counts using a static price table. real billing
runs on azure's invoice; this is a guard rail, not an invoice. document it in the readme.

in-memory: a restart resets the counter. fine for a personal project; for multi-replica
deployments, swap the counter for redis or postgres."""
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime

log = logging.getLogger(__name__)


# usd per 1k tokens. only the deployments we actually use need to be here; anything missing
# falls back to a conservative gpt-4o assumption.
PRICES_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.00250, 0.01000),
    "gpt-4": (0.03000, 0.06000),
    "gpt-35-turbo": (0.00050, 0.00150),
}
FALLBACK_PRICE = (0.00250, 0.01000)


class BudgetExceeded(RuntimeError):
    pass


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
        """raise BudgetExceeded if today's spend already meets or exceeds the limit."""
        t = now or datetime.now(UTC)
        with self._lock:
            self._roll_if_new_day(t)
            if self._state.spent_usd >= self.limit:
                raise BudgetExceeded(
                    f"daily llm budget exhausted: spent ${self._state.spent_usd:.4f} >= limit ${self.limit:.2f}"
                )

    def record(self, model: str, prompt_tokens: int, completion_tokens: int, now: datetime | None = None) -> float:
        in_price, out_price = PRICES_PER_1K.get(model, FALLBACK_PRICE)
        cost = (prompt_tokens / 1000.0) * in_price + (completion_tokens / 1000.0) * out_price
        t = now or datetime.now(UTC)
        with self._lock:
            self._roll_if_new_day(t)
            self._state.spent_usd += cost
            return self._state.spent_usd

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._state.spent_usd


# module-level singleton wired in llm.py
from backend.config import LLM_DAILY_BUDGET_USD  # noqa: E402

budget = DailyBudget(LLM_DAILY_BUDGET_USD)
