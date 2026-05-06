import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import execute_values
from psycopg2.pool import SimpleConnectionPool

from backend.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER

log = logging.getLogger(__name__)

_pool: SimpleConnectionPool | None = None


def init_pool(minconn: int = 1, maxconn: int = 10) -> None:
    global _pool
    if _pool is not None:
        return
    _pool = SimpleConnectionPool(
        minconn,
        maxconn,
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME,
    )
    log.info("postgres pool initialized host=%s db=%s", DB_HOST, DB_NAME)


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None


@contextmanager
def conn() -> Iterator[psycopg2.extensions.connection]:
    if _pool is None:
        init_pool()
    assert _pool is not None
    c = _pool.getconn()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        _pool.putconn(c)


def save_analysis(trace_id: str, log_text: str, analysis: str, model: str, prompt_version: str = "v1") -> None:
    save_analyses_batch([(trace_id, log_text, analysis, model, prompt_version)])


def save_analyses_batch(rows: list[tuple[str, str, str, str, str]]) -> None:
    """insert many analyses in a single round-trip via execute_values."""
    if not rows:
        return
    with conn() as c, c.cursor() as cur:
        execute_values(
            cur,
            "insert into analyses (trace_id, log_text, analysis, model, prompt_version) values %s",
            rows,
            page_size=500,
        )


def get_analysis(trace_id: str) -> dict | None:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            select trace_id, log_text, analysis, model, prompt_version, created_at
            from analyses
            where trace_id = %s
            order by created_at desc
            limit 1
            """,
            (trace_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "trace_id": row[0],
            "log_text": row[1],
            "analysis": row[2],
            "model": row[3],
            "prompt_version": row[4],
            "created_at": row[5].isoformat(),
        }


def save_raw_logs_batch(entries: list[dict]) -> None:
    """persist many raw log records via execute_values. entries without `trace_id` or
    `timestamp` are dropped (the schema forbids null trace_id and the correlator drops them
    anyway)."""
    if not entries:
        return
    rows: list[tuple[str, str, str, str, str | None]] = []
    for e in entries:
        trace_id = e.get("trace_id")
        ts = e.get("timestamp")
        if not trace_id or not ts:
            continue
        # everything not already a column lands in payload as jsonb
        payload = {k: v for k, v in e.items() if k not in {"trace_id", "level", "message", "timestamp"}}
        rows.append(
            (trace_id, e.get("level", "INFO"), e.get("message", ""), ts, json.dumps(payload) if payload else None)
        )
    if not rows:
        return
    with conn() as c, c.cursor() as cur:
        execute_values(
            cur,
            "insert into raw_logs (trace_id, level, message, ts, payload) values %s",
            rows,
            page_size=1000,
        )
