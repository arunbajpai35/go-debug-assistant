import logging

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from backend import db, metrics, pipeline
from backend.config import CORS_ORIGINS, MAX_LOGS_PER_REQUEST, WINDOW_SECONDS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger(__name__)


class LogEntry(BaseModel):
    timestamp: str
    level: str = "INFO"
    message: str
    trace_id: str


class AnalyzeRequest(BaseModel):
    logs: list[LogEntry] = Field(min_length=1)
    window_seconds: int | None = None


app = FastAPI(title="debug-assistant", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    try:
        db.init_pool()
    except Exception:
        log.exception("postgres pool init failed; api will start but persistence is unavailable")


@app.on_event("shutdown")
def _shutdown() -> None:
    db.close_pool()


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/metrics")
def prom_metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/analyze")
def analyze(req: AnalyzeRequest) -> dict:
    if len(req.logs) > MAX_LOGS_PER_REQUEST:
        raise HTTPException(413, f"too many logs (max {MAX_LOGS_PER_REQUEST})")
    metrics.logs_ingested.labels(source="http").inc(len(req.logs))
    window = req.window_seconds or WINDOW_SECONDS
    results = pipeline.process([l.model_dump() for l in req.logs], window_seconds=window)
    return {"results": results, "count": len(results)}


@app.get("/analysis/{trace_id}")
def get_analysis(trace_id: str) -> dict:
    row = db.get_analysis(trace_id)
    if not row:
        raise HTTPException(404, "analysis not found")
    return row
