import io
import json
import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.log_setup import JsonFormatter, request_id_ctx


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def _record(msg: str, **extras) -> logging.LogRecord:
    rec = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    for k, v in extras.items():
        setattr(rec, k, v)
    return rec


def test_json_formatter_emits_required_fields():
    out = _format(_record("hello"))
    assert out["msg"] == "hello"
    assert out["level"] == "INFO"
    assert out["logger"] == "t"
    assert "ts" in out and out["ts"].endswith("Z")


def test_json_formatter_includes_request_id_from_contextvar():
    token = request_id_ctx.set("rid-abc")
    try:
        out = _format(_record("with rid"))
    finally:
        request_id_ctx.reset(token)
    assert out["request_id"] == "rid-abc"


def test_json_formatter_omits_request_id_when_unset():
    out = _format(_record("no rid"))
    assert "request_id" not in out


def test_json_formatter_promotes_extras():
    out = _format(_record("with extras", logs_count=42, window_seconds=60))
    assert out["logs_count"] == 42
    assert out["window_seconds"] == 60


def test_json_formatter_renders_unjsonable_extras_as_repr():
    class Weird:
        def __repr__(self): return "<weird>"
    out = _format(_record("weird", weird=Weird()))
    assert out["weird"] == "<weird>"


def test_request_id_middleware_echoes_header_back():
    with patch("backend.db.init_pool"), patch("backend.db.close_pool"):
        from backend.api import app
        with TestClient(app) as c:
            r = c.get("/healthz", headers={"x-request-id": "test-rid-123"})
    assert r.headers["x-request-id"] == "test-rid-123"


def test_request_id_middleware_generates_when_absent():
    with patch("backend.db.init_pool"), patch("backend.db.close_pool"):
        from backend.api import app
        with TestClient(app) as c:
            r = c.get("/healthz")
    assert "x-request-id" in r.headers
    assert len(r.headers["x-request-id"]) >= 16


def test_log_records_emitted_during_request_carry_request_id():
    """end-to-end: middleware sets contextvar, JsonFormatter reads it.
    /analyze logs one line per request which gives us a reliable line to assert against."""
    buf = io.StringIO()
    h = logging.StreamHandler(buf)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    prev = root.handlers[:]
    root.handlers = [h]
    root.setLevel(logging.INFO)
    try:
        with (
            patch("backend.db.init_pool"),
            patch("backend.db.close_pool"),
            patch("backend.api.pipeline.process", return_value=[]),
        ):
            from backend.api import app
            with TestClient(app) as c:
                c.post(
                    "/analyze",
                    json={
                        "logs": [
                            {
                                "timestamp": "2026-05-06T10:00:00Z",
                                "level": "ERROR",
                                "message": "x",
                                "trace_id": "t",
                            }
                        ]
                    },
                    headers={"x-request-id": "rid-xyz"},
                )
    finally:
        root.handlers = prev

    lines = [json.loads(line) for line in buf.getvalue().splitlines() if line.strip().startswith("{")]
    rids = {line.get("request_id") for line in lines if "request_id" in line}
    assert "rid-xyz" in rids
