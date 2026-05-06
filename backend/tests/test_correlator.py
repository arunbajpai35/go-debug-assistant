from backend.correlator import correlate, format_window, parse_ts


def test_parse_ts_z_suffix():
    assert parse_ts("2026-05-06T10:00:00Z").tzinfo is not None


def test_parse_ts_offset():
    offset = parse_ts("2026-05-06T10:00:00+05:30").utcoffset()
    assert offset is not None
    assert offset.seconds == 5 * 3600 + 30 * 60


def test_correlate_groups_by_trace_within_window():
    logs = [
        {"timestamp": "2026-05-06T10:00:00Z", "trace_id": "a", "level": "ERROR", "message": "boom"},
        {"timestamp": "2026-05-06T10:00:30Z", "trace_id": "b", "level": "INFO", "message": "neighbour"},
        {"timestamp": "2026-05-06T10:05:00Z", "trace_id": "a", "level": "ERROR", "message": "boom2"},
    ]
    out = correlate(logs, window_seconds=60)
    assert set(out.keys()) == {"a", "b"}
    # trace a's window stretches across both its entries plus neighbours within 60s of either end
    assert any(e["message"] == "neighbour" for e in out["a"])


def test_correlate_drops_entries_without_trace_id():
    logs = [
        {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "no trace"},
        {"timestamp": "2026-05-06T10:00:01Z", "trace_id": "a", "level": "ERROR", "message": "ok"},
    ]
    out = correlate(logs, window_seconds=10)
    assert list(out.keys()) == ["a"]


def test_format_window_includes_timestamps_and_levels():
    text = format_window(
        [
            {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "x"},
            {"timestamp": "2026-05-06T10:00:01Z", "level": "WARN", "message": "y"},
        ]
    )
    assert "ERROR: x" in text
    assert "WARN: y" in text
