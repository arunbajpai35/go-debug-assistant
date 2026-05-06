"""real postgres integration: applies migrations against a live db, runs a request through
/analyze with the llm stubbed, then reads it back via /analysis/{trace_id}.

skipped unless DB_HOST is set so unit-test runs stay fast and offline. ci sets it via the
postgres service container."""
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("INTEGRATION") or not os.getenv("DB_HOST"),
    reason="integration test: requires INTEGRATION=1 and a reachable DB_HOST",
)


@pytest.fixture(scope="module")
def app_client():
    from backend import db
    from backend.migrate import run_migrations

    db.init_pool()
    run_migrations()

    from backend.api import app

    with TestClient(app) as c:
        yield c

    db.close_pool()


def test_analyze_then_fetch_round_trip(app_client):
    with patch("backend.pipeline.llm.analyze", return_value=("root_cause: stub", "stub-model")):
        post = app_client.post(
            "/analyze",
            json={
                "logs": [
                    {
                        "timestamp": "2026-05-06T10:00:00Z",
                        "level": "ERROR",
                        "message": "db timeout integration",
                        "trace_id": "int-trace-1",
                    }
                ]
            },
        )
    assert post.status_code == 200
    body = post.json()
    assert body["count"] == 1
    assert body["results"][0]["analysis"] == "root_cause: stub"

    fetched = app_client.get("/analysis/int-trace-1")
    assert fetched.status_code == 200
    row = fetched.json()
    assert row["trace_id"] == "int-trace-1"
    assert row["analysis"] == "root_cause: stub"
    assert row["model"] == "stub-model"


def test_readyz_against_real_db(app_client):
    r = app_client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
