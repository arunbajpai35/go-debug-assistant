"""json structured logging + request_id contextvar.

format (one line per record):
    {"ts": "2026-05-06T10:00:00.123Z", "level": "INFO", "logger": "...", "msg": "...",
     "request_id": "...", "trace_id": "...", "span_id": "...", ...extras}

`request_id` flows from the http middleware in api.py.
`trace_id` / `span_id` come from the active opentelemetry span when one is open.

set LOG_FORMAT=text to opt out (useful when running under a debugger).
"""
import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from opentelemetry import trace

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
    "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
    "relativeCreated", "thread", "threadName", "processName", "process", "message",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_ctx.get()
        if rid:
            out["request_id"] = rid

        span = trace.get_current_span()
        ctx = span.get_span_context() if span else None
        if ctx and ctx.is_valid:
            out["trace_id"] = format(ctx.trace_id, "032x")
            out["span_id"] = format(ctx.span_id, "016x")

        for k, v in record.__dict__.items():
            if k not in _RESERVED and not k.startswith("_") and k not in out:
                try:
                    json.dumps(v)
                    out[k] = v
                except TypeError:
                    out[k] = repr(v)

        if record.exc_info:
            out["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(out, ensure_ascii=False)


def configure(level: str | int = "INFO") -> None:
    """install the json formatter on the root logger. idempotent."""
    fmt = os.getenv("LOG_FORMAT", "json").lower()
    handler = logging.StreamHandler(sys.stdout)
    if fmt == "text":
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    # remove any pre-existing handlers (uvicorn / fastapi may install their own)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)
