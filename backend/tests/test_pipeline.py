from unittest.mock import patch

from backend import pipeline

SAMPLE_LOGS = [
    {"timestamp": "2026-05-06T10:00:00Z", "trace_id": "t1", "level": "ERROR", "message": "boom"},
    {"timestamp": "2026-05-06T10:00:01Z", "trace_id": "t1", "level": "ERROR", "message": "boom2"},
    {"timestamp": "2026-05-06T10:00:02Z", "trace_id": "t2", "level": "INFO", "message": "unrelated"},
]


def test_pipeline_runs_one_llm_call_per_trace_bundle_and_batches_persist():
    with (
        patch("backend.pipeline.llm.analyze", return_value=("root_cause: db timeout", "gpt-4o-mini")) as analyze,
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert {r["trace_id"] for r in results} == {"t1", "t2"}
    assert analyze.call_count == 2
    # batched persist: one call with both rows, not two single-row inserts
    assert save_batch.call_count == 1
    assert len(save_batch.call_args.args[0]) == 2
    for r in results:
        assert r["analysis"].startswith("root_cause:")
        assert r["model"] == "gpt-4o-mini"


def test_pipeline_skips_failed_bundle_and_persists_successful_one():
    calls = {"n": 0}

    def fail_first(text: str, window: int):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated rate limit")
        return ("ok", "gpt-4o-mini")

    with (
        patch("backend.pipeline.llm.analyze", side_effect=fail_first),
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert len(results) == 1
    assert save_batch.call_count == 1
    assert len(save_batch.call_args.args[0]) == 1


def test_pipeline_does_not_persist_when_llm_fails_for_all():
    with (
        patch("backend.pipeline.llm.analyze", side_effect=RuntimeError("down")),
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert results == []
    assert save_batch.call_count == 0
