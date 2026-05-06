from unittest.mock import patch

from backend import pipeline

SAMPLE_LOGS = [
    {"timestamp": "2026-05-06T10:00:00Z", "trace_id": "t1", "level": "ERROR", "message": "boom"},
    {"timestamp": "2026-05-06T10:00:01Z", "trace_id": "t1", "level": "ERROR", "message": "boom2"},
    {"timestamp": "2026-05-06T10:00:02Z", "trace_id": "t2", "level": "INFO", "message": "unrelated"},
]


def test_pipeline_runs_one_llm_call_per_trace_bundle_and_batches_persist():
    with (
        patch("backend.pipeline.llm.analyze", return_value=("root_cause: db timeout", "gpt-4o-mini", "v2")) as analyze,
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
        patch("backend.pipeline.db.save_raw_logs_batch") as save_raw,
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert {r["trace_id"] for r in results} == {"t1", "t2"}
    assert analyze.call_count == 2
    assert save_batch.call_count == 1
    assert len(save_batch.call_args.args[0]) == 2
    # raw_logs persistence runs once with all input logs (drops untraced ones inside db.py)
    assert save_raw.call_count == 1
    assert save_raw.call_args.args[0] == SAMPLE_LOGS
    for r in results:
        assert r["analysis"].startswith("root_cause:")
        assert r["model"] == "gpt-4o-mini"


def test_pipeline_skips_failed_bundle_and_persists_successful_one():
    calls = {"n": 0}

    def fail_first(text: str, window: int):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated rate limit")
        return ("ok", "gpt-4o-mini", "v2")

    with (
        patch("backend.pipeline.llm.analyze", side_effect=fail_first),
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
        patch("backend.pipeline.db.save_raw_logs_batch"),
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert len(results) == 1
    assert save_batch.call_count == 1
    assert len(save_batch.call_args.args[0]) == 1


def test_pipeline_does_not_persist_analyses_when_llm_fails_for_all():
    with (
        patch("backend.pipeline.llm.analyze", side_effect=RuntimeError("down")),
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
        patch("backend.pipeline.db.save_raw_logs_batch") as save_raw,
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert results == []
    assert save_batch.call_count == 0
    # raw_logs still persisted even when llm is fully down — that's the whole point of having them
    assert save_raw.call_count == 1


def test_pipeline_continues_when_raw_logs_persistence_fails():
    """raw_logs is best-effort: a save failure must not block correlation + analysis."""
    with (
        patch("backend.pipeline.llm.analyze", return_value=("ok", "gpt-4o-mini", "v2")),
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
        patch("backend.pipeline.db.save_raw_logs_batch", side_effect=RuntimeError("disk full")),
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert len(results) == 2
    assert save_batch.call_count == 1
