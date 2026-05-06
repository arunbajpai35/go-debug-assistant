from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.rate_limit import SlidingWindow


def test_sliding_window_allows_under_limit():
    sw = SlidingWindow(limit=3, window_seconds=60.0)
    for i in range(3):
        allowed, retry = sw.check("ip-1", now=100.0 + i)
        assert allowed is True
        assert retry == 0.0


def test_sliding_window_denies_over_limit_with_retry_after():
    sw = SlidingWindow(limit=2, window_seconds=60.0)
    sw.check("ip-1", now=100.0)
    sw.check("ip-1", now=110.0)
    allowed, retry = sw.check("ip-1", now=120.0)
    assert allowed is False
    assert 0 < retry <= 60.0


def test_sliding_window_evicts_old_entries():
    sw = SlidingWindow(limit=2, window_seconds=60.0)
    sw.check("ip-1", now=0.0)
    sw.check("ip-1", now=10.0)
    # both fall outside the 60s window when we ask at t=200
    allowed, retry = sw.check("ip-1", now=200.0)
    assert allowed is True
    assert retry == 0.0


def test_sliding_window_isolates_per_key():
    sw = SlidingWindow(limit=1, window_seconds=60.0)
    sw.check("ip-1", now=0.0)
    allowed, _ = sw.check("ip-2", now=0.0)
    assert allowed is True


def test_analyze_returns_429_after_burst():
    with patch("backend.db.init_pool"), patch("backend.db.close_pool"):
        from backend import api
        api._rate_limiter.reset()
        api._rate_limiter.limit = 2
        from backend.api import app

        with TestClient(app) as c:
            payload = {
                "logs": [
                    {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "x", "trace_id": "t"}
                ]
            }
            with patch("backend.api.pipeline.process", return_value=[]):
                assert c.post("/analyze", json=payload).status_code == 200
                assert c.post("/analyze", json=payload).status_code == 200
                r = c.post("/analyze", json=payload)
                assert r.status_code == 429
                assert "retry-after" in {k.lower() for k in r.headers}


def test_rate_limit_does_not_apply_to_healthz():
    with patch("backend.db.init_pool"), patch("backend.db.close_pool"):
        from backend import api
        api._rate_limiter.reset()
        api._rate_limiter.limit = 1
        from backend.api import app

        with TestClient(app) as c:
            for _ in range(20):
                assert c.get("/healthz").status_code == 200
