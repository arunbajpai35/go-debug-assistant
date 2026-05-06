import logging
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from backend import db, log_setup, metrics, pipeline, tracing
from backend.budget import budget as llm_budget
from backend.config import (
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    CORS_ORIGINS,
    LLM_DAILY_BUDGET_USD,
    MAX_LOGS_PER_REQUEST,
    RATE_LIMIT_PER_MINUTE,
    WINDOW_SECONDS,
)
from backend.rate_limit import make_limiter

log_setup.configure()
tracing.init()
log = logging.getLogger(__name__)


class LogEntry(BaseModel):
    timestamp: str
    level: str = "INFO"
    message: str
    trace_id: str


class AnalyzeRequest(BaseModel):
    logs: list[LogEntry] = Field(min_length=1)
    window_seconds: int | None = None


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        db.init_pool()
    except Exception:
        log.exception("postgres pool init failed; api will start but persistence is unavailable")
    try:
        yield
    finally:
        await db.close_pool()


app = FastAPI(title="debug-assistant", version="0.8.0", lifespan=lifespan)
tracing.instrument_fastapi(app)

_RATE_LIMITED_PATHS = {"/analyze"}
_rate_limiter = make_limiter(limit=RATE_LIMIT_PER_MINUTE, window_seconds=60.0)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path not in _RATE_LIMITED_PATHS:
            return await call_next(request)
        ip = _client_ip(request)
        allowed, retry_after = _rate_limiter.check(ip)
        if not allowed:
            log.warning(
                "rate limit hit",
                extra={"ip": ip, "path": request.url.path, "retry_after_s": round(retry_after, 2)},
            )
            return Response(
                '{"detail":"rate limit exceeded"}',
                media_type="application/json",
                status_code=429,
                headers={"retry-after": str(int(retry_after) + 1)},
            )
        return await call_next(request)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = log_setup.request_id_ctx.set(rid)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = rid
            return response
        finally:
            log_setup.request_id_ctx.reset(token)


# add order = reverse of execution order. last add() runs outermost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestIdMiddleware)


@app.exception_handler(Exception)
async def _handle_unexpected(request: Request, exc: Exception) -> Response:
    """generic 500 handler — logs the full traceback but does NOT leak it to the client.
    fastapi's default returns "Internal Server Error" plain text; we replace it with a json
    body that carries the request_id for support workflows.

    rid is read directly from the request header instead of the contextvar — by the time
    the exception handler runs, BaseHTTPMiddleware may have already reset the contextvar."""
    log.exception("unhandled exception path=%s", request.url.path)
    rid = request.headers.get("x-request-id") or log_setup.request_id_ctx.get() or "unknown"
    body = f'{{"detail":"internal error","request_id":"{rid}"}}'
    return Response(body, media_type="application/json", status_code=500)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/version")
def version() -> dict:
    return {
        "version": app.version,
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "build_date": os.getenv("BUILD_DATE", "unknown"),
    }


@app.get("/budget")
def budget_status() -> dict:
    return {
        "limit_usd": LLM_DAILY_BUDGET_USD,
        "spent_usd": round(llm_budget.spent_usd, 6),
        "remaining_usd": round(max(LLM_DAILY_BUDGET_USD - llm_budget.spent_usd, 0.0), 6),
    }


@app.get("/readyz")
async def readyz() -> Response:
    try:
        await db.ping()
    except Exception as e:
        log.warning("readyz failed: %s", e)
        return Response('{"ok":false,"db":"down"}', media_type="application/json", status_code=503)
    return Response('{"ok":true}', media_type="application/json")


@app.get("/metrics")
def prom_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/analyze")
async def analyze(req: AnalyzeRequest) -> dict:
    if len(req.logs) > MAX_LOGS_PER_REQUEST:
        raise HTTPException(413, f"too many logs (max {MAX_LOGS_PER_REQUEST})")
    metrics.logs_ingested.labels(source="http").inc(len(req.logs))
    window = req.window_seconds or WINDOW_SECONDS
    payload = [entry.model_dump() for entry in req.logs]
    log.info("analyze accepted", extra={"logs_count": len(payload), "window_seconds": window})
    results = await pipeline.process(payload, window)
    log.info("analyze completed", extra={"results_count": len(results)})
    return {"results": results, "count": len(results)}


@app.get("/analysis/{trace_id}")
async def get_analysis(trace_id: str) -> dict:
    row = await db.get_analysis(trace_id)
    if not row:
        raise HTTPException(404, "analysis not found")
    return row
