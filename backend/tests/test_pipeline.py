from unittest.mock import patch

from backend import pipeline
from backend.llm_schema import AnalysisResult

SAMPLE_LOGS = [
    {"timestamp": "2026-05-06T10:00:00Z", "trace_id": "t1", "level": "ERROR", "message": "boom"},
    {"timestamp": "2026-05-06T10:00:01Z", "trace_id": "t1", "level": "ERROR", "message": "boom2"},
    {"timestamp": "2026-05-06T10:00:02Z", "trace_id": "t2", "level": "INFO", "message": "unrelated"},
]


def _result(text: str = "ok", **kw) -> AnalysisResult:
    base: dict = {"raw_text": text, "model": "gpt-4o-mini", "prompt_version": "v3"}
    base.update(kw)
    return AnalysisResult(**base)


def test_pipeline_runs_one_llm_call_per_trace_bundle_and_batches_persist():
    with (
        patch(
            "backend.pipeline.llm.analyze",
            return_value=_result(
                text='{"category":"db","root_cause":"db timeout","next_step":"check pool",'
                     '"evidence":["10:00:00"],"confidence":"high"}',
                category="db",
                root_cause="db timeout",
                next_step="check pool",
                evidence=["10:00:00"],
                confidence="high",
            ),
        ) as analyze,
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
        patch("backend.pipeline.db.save_raw_logs_batch") as save_raw,
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert {r["trace_id"] for r in results} == {"t1", "t2"}
    assert analyze.call_count == 2
    assert save_batch.call_count == 1
    rows = save_batch.call_args.args[0]
    assert len(rows) == 2
    # 10-tuple shape
    assert all(len(r) == 10 for r in rows)
    # parsed fields persisted
    assert all(r[5] == "db" for r in rows)
    assert all(r[6] == "db timeout" for r in rows)
    assert all(r[9] == "high" for r in rows)
    assert save_raw.call_count == 1


def test_pipeline_skips_failed_bundle_and_persists_successful_one():
    calls = {"n": 0}

    def fail_first(text: str, window: int):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated rate limit")
        return _result()

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
    assert save_raw.call_count == 1


def test_pipeline_continues_when_raw_logs_persistence_fails():
    with (
        patch("backend.pipeline.llm.analyze", return_value=_result()),
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
        patch("backend.pipeline.db.save_raw_logs_batch", side_effect=RuntimeError("disk full")),
    ):
        results = pipeline.process(SAMPLE_LOGS, window_seconds=60)

    assert len(results) == 2
    assert save_batch.call_count == 1


def test_pipeline_persists_nullable_structured_fields_for_v1_prompt():
    """v1 prompts return free text only — structured fields stay None."""
    with (
        patch("backend.pipeline.llm.analyze", return_value=_result(text="just some text", prompt_version="v1")),
        patch("backend.pipeline.db.save_analyses_batch") as save_batch,
        patch("backend.pipeline.db.save_raw_logs_batch"),
    ):
        pipeline.process(SAMPLE_LOGS, window_seconds=60)

    rows = save_batch.call_args.args[0]
    # category, root_cause, next_step, evidence_json, confidence should all be None
    for r in rows:
        assert r[5] is None
        assert r[6] is None
        assert r[7] is None
        assert r[8] is None
        assert r[9] is None
