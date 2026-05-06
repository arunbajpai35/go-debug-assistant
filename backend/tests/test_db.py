"""unit tests on shape-only logic. integration tests cover real db round-trips."""
from unittest.mock import MagicMock, patch

from backend import db


def test_save_raw_logs_batch_drops_entries_without_trace_id_or_timestamp():
    cur = MagicMock()
    fake_conn = MagicMock()
    fake_conn.__enter__.return_value = fake_conn
    fake_conn.__exit__.return_value = False
    fake_conn.cursor.return_value.__enter__.return_value = cur
    fake_conn.cursor.return_value.__exit__.return_value = False

    entries = [
        {"trace_id": "t1", "timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "ok"},
        {"timestamp": "2026-05-06T10:00:01Z", "level": "ERROR", "message": "no trace"},
        {"trace_id": "t3", "level": "ERROR", "message": "no ts"},
        {"trace_id": "t4", "timestamp": "2026-05-06T10:00:02Z", "level": "INFO", "message": "ok2", "extra": "kept"},
    ]

    with (
        patch("backend.db.conn", return_value=fake_conn),
        patch("backend.db.execute_values") as ev,
    ):
        db.save_raw_logs_batch(entries)

    ev.assert_called_once()
    rows = ev.call_args.args[2]
    assert {r[0] for r in rows} == {"t1", "t4"}
    # extras (any field not in the 4 columns) get rolled into payload jsonb
    payloads = {r[0]: r[4] for r in rows}
    assert payloads["t1"] is None
    assert "extra" in (payloads["t4"] or "")


def test_save_raw_logs_batch_no_op_on_empty_input():
    with patch("backend.db.execute_values") as ev:
        db.save_raw_logs_batch([])
    ev.assert_not_called()
