import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg2
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


def save_analysis(trace_id: str, log_text: str, analysis: str, model: str) -> None:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            insert into analyses (trace_id, log_text, analysis, model)
            values (%s, %s, %s, %s)
            """,
            (trace_id, log_text, analysis, model),
        )


def get_analysis(trace_id: str) -> dict | None:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            "select trace_id, log_text, analysis, model, created_at from analyses where trace_id = %s order by created_at desc limit 1",
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
            "created_at": row[4].isoformat(),
        }


def save_raw_log(trace_id: str, level: str, message: str, ts: str, payload: dict | None = None) -> None:
    with conn() as c, c.cursor() as cur:
        cur.execute(
            """
            insert into raw_logs (trace_id, level, message, ts, payload)
            values (%s, %s, %s, %s, %s)
            """,
            (trace_id, level, message, ts, json.dumps(payload) if payload else None),
        )
