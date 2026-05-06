"""real postgres integration: applies migrations against a live db, runs a request through
/analyze with the llm stubbed, then reads it back via /analysis/{trace_id}.

skipped unless DB_HOST is set so unit-test runs stay fast and offline. ci sets it via the
postgres service container."""
import os
import subprocess
import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.getenv("INTEGRATION") or not os.getenv("DB_HOST"),
    reason="integration test: requires INTEGRATION=1 and a reachable DB_HOST",
)


@pytest.fixture(scope="module")
def app_client():
    from backend import db

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    db.init_pool()

    from backend.api import app

    with TestClient(app) as c:
        yield c

    # the test client owns the fastapi lifespan loop and closes the pool there.
    # nothing further to do here.


def test_analyze_then_fetch_round_trip(app_client):
    from backend.llm_schema import AnalysisResult

    stub = AnalysisResult(
        raw_text='{"category":"db","root_cause":"stub","next_step":"x","evidence":[],"confidence":"low"}',
        model="stub-model",
        prompt_version="v3",
        category="db",
        root_cause="stub",
        next_step="x",
        evidence=[],
        confidence="low",
    )
    with patch("backend.pipeline.llm.analyze", AsyncMock(return_value=stub)):
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
    assert body["results"][0]["category"] == "db"

    fetched = app_client.get("/analysis/int-trace-1")
    assert fetched.status_code == 200
    row = fetched.json()
    assert row["trace_id"] == "int-trace-1"
    assert row["category"] == "db"
    assert row["root_cause"] == "stub"


def test_readyz_against_real_db(app_client):
    r = app_client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_raw_logs_persisted_during_analyze(app_client):
    """uses psycopg2 (sync) for the verification query — the runtime pool is asyncpg-bound to
    the testclient's lifespan loop, so a separate sync probe is the cleanest verification path."""
    import psycopg2

    from backend.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
    from backend.llm_schema import AnalysisResult

    stub = AnalysisResult(raw_text="stub", model="stub-model", prompt_version="v1")
    with patch("backend.pipeline.llm.analyze", AsyncMock(return_value=stub)):
        post = app_client.post(
            "/analyze",
            json={
                "logs": [
                    {
                        "timestamp": "2026-05-06T11:00:00Z",
                        "level": "WARN",
                        "message": "raw logs round-trip",
                        "trace_id": "raw-int-1",
                    }
                ]
            },
        )
    assert post.status_code == 200

    c = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, dbname=DB_NAME
    )
    try:
        with c.cursor() as cur:
            cur.execute("select count(*) from raw_logs where trace_id = %s", ("raw-int-1",))
            (count,) = cur.fetchone()
    finally:
        c.close()
    assert count == 1
