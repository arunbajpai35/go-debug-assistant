from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    # avoid touching real postgres at import / startup
    with (
        patch("backend.db.init_pool"),
        patch("backend.db.close_pool", AsyncMock()),
    ):
        from backend.api import app  # imported lazily so init_pool is patched
        with TestClient(app) as c:
            yield c


def test_healthz_returns_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_version_returns_metadata(client):
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert "git_sha" in body
    assert "build_date" in body


def test_metrics_exposes_prometheus_text(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    assert "logs_ingested_total" in body or "python_info" in body


def test_readyz_ok_when_db_ping_succeeds(client):
    with patch("backend.api.db.ping", AsyncMock()):
        r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_readyz_503_when_db_down(client):
    with patch("backend.api.db.ping", AsyncMock(side_effect=RuntimeError("connection refused"))):
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json() == {"ok": False, "db": "down"}


def test_analyze_validates_empty_logs(client):
    r = client.post("/analyze", json={"logs": []})
    assert r.status_code == 422


def test_analyze_validates_missing_required_fields(client):
    r = client.post("/analyze", json={"logs": [{"timestamp": "2026-05-06T10:00:00Z"}]})
    assert r.status_code == 422


def test_analyze_413_when_over_max_logs(client):
    too_many = [
        {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "x", "trace_id": "t"}
        for _ in range(5001)
    ]
    r = client.post("/analyze", json={"logs": too_many})
    assert r.status_code == 413
    assert "too many" in r.json()["detail"].lower()


def test_analyze_runs_pipeline_and_returns_results(client):
    canned = [{"trace_id": "t1", "log_text": "...", "analysis": "ok", "model": "stub"}]
    proc = AsyncMock(return_value=canned)
    with patch("backend.api.pipeline.process", proc):
        r = client.post(
            "/analyze",
            json={
                "logs": [
                    {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "boom", "trace_id": "t1"}
                ]
            },
        )
    assert r.status_code == 200
    assert r.json() == {"results": canned, "count": 1}
    proc.assert_awaited_once()


def test_analyze_uses_request_window_seconds_when_provided(client):
    proc = AsyncMock(return_value=[])
    with patch("backend.api.pipeline.process", proc):
        client.post(
            "/analyze",
            json={
                "logs": [
                    {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "x", "trace_id": "t"}
                ],
                "window_seconds": 5,
            },
        )
    args = proc.call_args.args
    assert args[1] == 5


def test_get_analysis_404_when_missing(client):
    with patch("backend.api.db.get_analysis", AsyncMock(return_value=None)):
        r = client.get("/analysis/unknown")
    assert r.status_code == 404


def test_get_analysis_returns_row_when_present(client):
    row = {"trace_id": "t1", "log_text": "x", "analysis": "y", "model": "z", "created_at": "2026-05-06T10:00:00+00:00"}
    with patch("backend.api.db.get_analysis", AsyncMock(return_value=row)):
        r = client.get("/analysis/t1")
    assert r.status_code == 200
    assert r.json() == row


def test_unhandled_exception_returns_500_with_request_id_and_no_traceback():
    """generic exception handler. body must be json with request_id, no stack trace leaked.
    a separate TestClient is used with raise_server_exceptions=False so exceptions reach the
    handler instead of being re-raised in the test."""
    with (
        patch("backend.db.init_pool"),
        patch("backend.db.close_pool", AsyncMock()),
    ):
        from backend.api import app

        with (
            TestClient(app, raise_server_exceptions=False) as c,
            patch("backend.api.db.get_analysis", AsyncMock(side_effect=RuntimeError("boom"))),
        ):
            r = c.get("/analysis/t1", headers={"x-request-id": "rid-500"})
    assert r.status_code == 500
    body = r.json()
    assert body["detail"] == "internal error"
    assert body["request_id"] == "rid-500"
    assert "Traceback" not in r.text
    assert "RuntimeError" not in r.text


def test_cors_preflight_respects_configured_methods(client):
    r = client.options(
        "/analyze",
        headers={
            "origin": "http://localhost:3000",
            "access-control-request-method": "POST",
            "access-control-request-headers": "content-type",
        },
    )
    assert r.status_code == 200
    # only the configured methods should be advertised
    allowed = r.headers.get("access-control-allow-methods", "")
    assert "POST" in allowed
    assert "DELETE" not in allowed
