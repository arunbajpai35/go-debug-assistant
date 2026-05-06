"""tests for redis-backed rate limit + budget. fakeredis stands in for a real broker."""
import time
from datetime import UTC, datetime, timedelta

import fakeredis
import pytest

from backend.budget import BudgetExceeded, RedisDailyBudget
from backend.rate_limit import RedisSlidingWindow


@pytest.fixture()
def fr():
    return fakeredis.FakeStrictRedis(decode_responses=True)


def test_redis_sliding_window_allows_under_limit(fr):
    sw = RedisSlidingWindow(fr, limit=3, window_seconds=60.0, prefix="t1")
    for i in range(3):
        allowed, retry = sw.check("ip-1", now=time.time() + i)
        assert allowed is True
        assert retry == 0.0


def test_redis_sliding_window_denies_over_limit(fr):
    sw = RedisSlidingWindow(fr, limit=2, window_seconds=60.0, prefix="t2")
    base = time.time()
    sw.check("ip-1", now=base)
    sw.check("ip-1", now=base + 1)
    allowed, retry = sw.check("ip-1", now=base + 2)
    assert allowed is False
    assert 0 < retry <= 60.0


def test_redis_sliding_window_evicts_old_entries(fr):
    sw = RedisSlidingWindow(fr, limit=2, window_seconds=60.0, prefix="t3")
    sw.check("ip-1", now=1000.0)
    sw.check("ip-1", now=1010.0)
    allowed, _ = sw.check("ip-1", now=1200.0)  # 60s window expired
    assert allowed is True


def test_redis_sliding_window_isolates_per_key(fr):
    sw = RedisSlidingWindow(fr, limit=1, window_seconds=60.0, prefix="t4")
    sw.check("ip-1", now=1000.0)
    allowed, _ = sw.check("ip-2", now=1000.0)
    assert allowed is True


def test_redis_budget_record_accumulates(fr):
    b = RedisDailyBudget(fr, daily_limit_usd=10.0, prefix="bt1")
    spent = b.record("gpt-4o-mini", 1000, 1000)
    assert spent == pytest.approx(0.00075, abs=1e-9)
    spent = b.record("gpt-4o-mini", 1000, 1000)
    assert spent == pytest.approx(0.00150, abs=1e-9)


def test_redis_budget_check_passes_when_under_limit(fr):
    b = RedisDailyBudget(fr, daily_limit_usd=10.0, prefix="bt2")
    b.record("gpt-4o-mini", 1000, 1000)
    b.check()  # no raise


def test_redis_budget_check_raises_when_over_limit(fr):
    b = RedisDailyBudget(fr, daily_limit_usd=0.0001, prefix="bt3")
    b.record("gpt-4o-mini", 1000, 1000)
    with pytest.raises(BudgetExceeded):
        b.check()


def test_redis_budget_separate_days_dont_collide(fr):
    b = RedisDailyBudget(fr, daily_limit_usd=10.0, prefix="bt4")
    day1 = datetime(2026, 5, 6, 12, tzinfo=UTC)
    day2 = day1 + timedelta(days=1)
    b.record("gpt-4o-mini", 1000, 1000, now=day1)
    spent_day2 = b.record("gpt-4o-mini", 500, 500, now=day2)
    # day2's counter is independent of day1's
    assert spent_day2 == pytest.approx((500 / 1000) * 0.00015 + (500 / 1000) * 0.00060, abs=1e-9)


def test_redis_budget_multi_replica_share_state(fr):
    """two budget instances pointed at the same redis keys see each other's spend
    — that's the whole point of moving this out of memory."""
    a = RedisDailyBudget(fr, daily_limit_usd=10.0, prefix="bt5")
    b = RedisDailyBudget(fr, daily_limit_usd=10.0, prefix="bt5")
    a.record("gpt-4o-mini", 1000, 1000)
    assert b.spent_usd == pytest.approx(a.spent_usd, abs=1e-9)


def test_redis_sliding_window_multi_replica_share_counter(fr):
    a = RedisSlidingWindow(fr, limit=2, window_seconds=60.0, prefix="rl5")
    b = RedisSlidingWindow(fr, limit=2, window_seconds=60.0, prefix="rl5")
    a.check("ip-1", now=1000.0)
    a.check("ip-1", now=1001.0)
    # third hit, but on the other 'replica' — it should still see saturated
    allowed, _ = b.check("ip-1", now=1002.0)
    assert allowed is False
