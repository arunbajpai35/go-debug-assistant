import pytest

from backend.circuit_breaker import CircuitBreaker, CircuitOpen, State


def test_starts_closed_and_allows_calls():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)
    cb.before_call(now=0.0)
    assert cb.state is State.CLOSED


def test_opens_after_threshold_consecutive_failures():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)
    cb.on_failure(now=0.0)
    cb.on_failure(now=0.1)
    assert cb.state is State.CLOSED  # not yet
    cb.on_failure(now=0.2)
    assert cb.state is State.OPEN


def test_open_circuit_refuses_calls():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
    cb.on_failure(now=0.0)
    assert cb.state is State.OPEN
    with pytest.raises(CircuitOpen):
        cb.before_call(now=0.5)


def test_success_in_closed_state_resets_failure_counter():
    cb = CircuitBreaker(failure_threshold=3, cooldown_seconds=10)
    cb.on_failure(now=0.0)
    cb.on_failure(now=0.1)
    cb.on_success()
    cb.on_failure(now=0.2)
    cb.on_failure(now=0.3)
    assert cb.state is State.CLOSED  # the prior failures were wiped


def test_transitions_to_half_open_after_cooldown():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
    cb.on_failure(now=0.0)  # open
    # before cooldown elapses, still open
    with pytest.raises(CircuitOpen):
        cb.before_call(now=5.0)
    # past cooldown, before_call moves us to HALF_OPEN and allows the trial
    cb.before_call(now=11.0)
    assert cb.state is State.HALF_OPEN


def test_half_open_success_closes_circuit():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
    cb.on_failure(now=0.0)
    cb.before_call(now=11.0)  # -> half_open + allowed
    cb.on_success()
    assert cb.state is State.CLOSED


def test_half_open_failure_reopens_circuit_with_reset_timer():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
    cb.on_failure(now=0.0)
    cb.before_call(now=11.0)  # half_open
    cb.on_failure(now=11.0)
    assert cb.state is State.OPEN
    # cooldown timer reset; not allowed at t=15 (4s after re-open)
    with pytest.raises(CircuitOpen):
        cb.before_call(now=15.0)
    # but allowed at t=22 (11s after re-open)
    cb.before_call(now=22.0)
    assert cb.state is State.HALF_OPEN


def test_reset_clears_state():
    cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=10)
    cb.on_failure(now=0.0)
    assert cb.state is State.OPEN
    cb.reset()
    assert cb.state is State.CLOSED
    cb.before_call(now=0.5)
