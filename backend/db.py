"""async postgres access via sqlalchemy core + asyncpg.

migrations still use psycopg2 (alembic env.py) — those run once at deploy time and don't need
async. only the request/worker hot path is async."""
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from backend.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
from backend.correlator import parse_ts

log = logging.getLogger(__name__)

_engine: AsyncEngine | None = None


def _url() -> str:
    return f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"


def init_pool(min_size: int = 1, max_size: int = 10) -> None:
    """create the async engine. idempotent."""
    global _engine
    if _engine is not None:
        return
    _engine = create_async_engine(
        _url(),
        pool_size=max_size,
        pool_pre_ping=True,
        future=True,
    )
    log.info("asyncpg pool initialized host=%s db=%s", DB_HOST, DB_NAME)


async def close_pool() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


@asynccontextmanager
async def conn() -> AsyncIterator[AsyncConnection]:
    if _engine is None:
        init_pool()
    assert _engine is not None
    async with _engine.begin() as c:
        yield c


AnalysisRow = tuple[
    str,           # trace_id
    str,           # log_text
    str,           # analysis (raw text)
    str,           # model
    str,           # prompt_version
    str | None,    # category
    str | None,    # root_cause
    str | None,    # next_step
    str | None,    # evidence (json-encoded list, or null)
    str | None,    # confidence
]


_INSERT_ANALYSIS = text(
    "insert into analyses "
    "(trace_id, log_text, analysis, model, prompt_version, "
    " category, root_cause, next_step, evidence, confidence) "
    "values (:trace_id, :log_text, :analysis, :model, :prompt_version, "
    " :category, :root_cause, :next_step, "
    " cast(:evidence as jsonb), :confidence)"
)


async def save_analysis(
    trace_id: str,
    log_text: str,
    analysis: str,
    model: str,
    prompt_version: str = "v1",
) -> None:
    await save_analyses_batch([(trace_id, log_text, analysis, model, prompt_version, None, None, None, None, None)])


async def save_analyses_batch(rows: list[AnalysisRow]) -> None:
    if not rows:
        return
    params = [
        {
            "trace_id": r[0],
            "log_text": r[1],
            "analysis": r[2],
            "model": r[3],
            "prompt_version": r[4],
            "category": r[5],
            "root_cause": r[6],
            "next_step": r[7],
            "evidence": r[8],
            "confidence": r[9],
        }
        for r in rows
    ]
    async with conn() as c:
        await c.execute(_INSERT_ANALYSIS, params)


_GET_ANALYSIS = text(
    """
    select trace_id, log_text, analysis, model, prompt_version,
           category, root_cause, next_step, evidence, confidence, created_at
    from analyses
    where trace_id = :trace_id
    order by created_at desc
    limit 1
    """
)


async def get_analysis(trace_id: str) -> dict[str, Any] | None:
    async with conn() as c:
        row = (await c.execute(_GET_ANALYSIS, {"trace_id": trace_id})).first()
        if row is None:
            return None
        return {
            "trace_id": row[0],
            "log_text": row[1],
            "analysis": row[2],
            "model": row[3],
            "prompt_version": row[4],
            "category": row[5],
            "root_cause": row[6],
            "next_step": row[7],
            "evidence": row[8],
            "confidence": row[9],
            "created_at": row[10].isoformat(),
        }


_INSERT_RAW_LOG = text(
    "insert into raw_logs (trace_id, level, message, ts, payload) "
    "values (:trace_id, :level, :message, :ts, cast(:payload as jsonb))"
)


async def save_raw_logs_batch(entries: list[dict]) -> None:
    if not entries:
        return
    params: list[dict] = []
    for e in entries:
        trace_id = e.get("trace_id")
        ts = e.get("timestamp")
        if not trace_id or not ts:
            continue
        try:
            parsed_ts = parse_ts(ts)
        except ValueError:
            continue
        payload = {k: v for k, v in e.items() if k not in {"trace_id", "level", "message", "timestamp"}}
        params.append(
            {
                "trace_id": trace_id,
                "level": e.get("level", "INFO"),
                "message": e.get("message", ""),
                "ts": parsed_ts,
                "payload": json.dumps(payload) if payload else None,
            }
        )
    if not params:
        return
    async with conn() as c:
        await c.execute(_INSERT_RAW_LOG, params)


async def ping() -> None:
    """raises if the db is unreachable. used by /readyz."""
    async with conn() as c:
        await c.execute(text("select 1"))
