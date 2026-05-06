from datetime import UTC, datetime, timedelta

import pytest

from backend.budget import BudgetExceeded, DailyBudget


def test_record_accumulates_known_model_cost():
    b = DailyBudget(daily_limit_usd=10.0)
    spent = b.record("gpt-4o-mini", prompt_tokens=1000, completion_tokens=1000)
    # 1000/1000 * 0.00015 + 1000/1000 * 0.00060 = 0.00075
    assert spent == pytest.approx(0.00075, abs=1e-9)


def test_record_uses_fallback_for_unknown_model():
    b = DailyBudget(daily_limit_usd=10.0)
    spent = b.record("custom-deployment-x", prompt_tokens=1000, completion_tokens=1000)
    # fallback = (0.00250, 0.01000)
    assert spent == pytest.approx(0.00250 + 0.01000, abs=1e-9)


def test_check_passes_when_under_limit():
    b = DailyBudget(daily_limit_usd=1.0)
    b.record("gpt-4o-mini", 1000, 1000)
    b.check()  # no raise


def test_check_raises_when_over_limit():
    b = DailyBudget(daily_limit_usd=0.0001)
    b.record("gpt-4o-mini", 1000, 1000)
    with pytest.raises(BudgetExceeded) as ei:
        b.check()
    assert "exhausted" in str(ei.value)


def test_state_resets_at_utc_midnight():
    b = DailyBudget(daily_limit_usd=10.0)
    today = datetime(2026, 5, 6, 23, 30, tzinfo=UTC)
    tomorrow = today + timedelta(hours=1)
    b.record("gpt-4o-mini", 1000, 1000, now=today)
    assert b.spent_usd > 0

    # checking on the next utc day rolls the counter back to zero
    b.check(now=tomorrow)
    assert b.spent_usd == 0


def test_record_after_rollover_starts_fresh():
    b = DailyBudget(daily_limit_usd=10.0)
    day1 = datetime(2026, 5, 6, 12, tzinfo=UTC)
    day2 = day1 + timedelta(days=1)
    b.record("gpt-4o-mini", 1000, 1000, now=day1)
    spent = b.record("gpt-4o-mini", 500, 500, now=day2)
    # the day1 spend should be gone; spent should be only the day2 portion
    assert spent == pytest.approx((500/1000) * 0.00015 + (500/1000) * 0.00060, abs=1e-9)
