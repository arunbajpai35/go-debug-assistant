"""unit tests on shape-only logic. integration tests cover real db round-trips."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import db


@pytest.mark.asyncio
async def test_save_raw_logs_batch_drops_entries_without_trace_id_or_timestamp():
    fake_conn = MagicMock()
    fake_conn.execute = AsyncMock()

    class _Ctx:
        async def __aenter__(self_): return fake_conn
        async def __aexit__(self_, *a): return False

    entries = [
        {"trace_id": "t1", "timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "ok"},
        {"timestamp": "2026-05-06T10:00:01Z", "level": "ERROR", "message": "no trace"},
        {"trace_id": "t3", "level": "ERROR", "message": "no ts"},
        {"trace_id": "t4", "timestamp": "2026-05-06T10:00:02Z", "level": "INFO", "message": "ok2", "extra": "kept"},
    ]

    with patch("backend.db.conn", return_value=_Ctx()):
        await db.save_raw_logs_batch(entries)

    fake_conn.execute.assert_awaited_once()
    params = fake_conn.execute.call_args.args[1]
    trace_ids = {p["trace_id"] for p in params}
    assert trace_ids == {"t1", "t4"}
    payloads = {p["trace_id"]: p["payload"] for p in params}
    assert payloads["t1"] is None
    assert "extra" in (payloads["t4"] or "")


@pytest.mark.asyncio
async def test_save_raw_logs_batch_no_op_on_empty_input():
    fake_conn = MagicMock()
    fake_conn.execute = AsyncMock()

    class _Ctx:
        async def __aenter__(self_): return fake_conn
        async def __aexit__(self_, *a): return False

    with patch("backend.db.conn", return_value=_Ctx()):
        await db.save_raw_logs_batch([])

    fake_conn.execute.assert_not_called()
