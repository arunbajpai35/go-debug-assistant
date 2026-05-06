from unittest.mock import MagicMock, patch

from backend import kafka_worker
from backend.config import KAFKA_DLQ_TOPIC, KAFKA_MAX_BUNDLE_RETRIES
from backend.kafka_offsets import OffsetTracker


def _bundle(trace_id: str = "t1", n: int = 2) -> list[dict]:
    return [
        {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": f"m{i}", "trace_id": trace_id}
        for i in range(n)
    ]


def _tracker_for(trace_id: str, partition: int = 0, offsets: tuple[int, ...] = (0, 1)) -> OffsetTracker:
    t = OffsetTracker()
    for o in offsets:
        t.add("debug.logs", partition, o, trace_id)
    return t


def test_flush_commits_per_partition_on_success_and_drops_retry_state():
    buffers = {"t1": _bundle("t1")}
    last_seen = {"t1": 100.0}
    retry_count = {"t1": 1}
    tracker = _tracker_for("t1")
    consumer = MagicMock()
    producer = MagicMock()

    with patch.object(kafka_worker.pipeline, "process", return_value=[{"trace_id": "t1"}]):
        kafka_worker._flush("t1", buffers, last_seen, retry_count, tracker, consumer, producer)

    consumer.commit.assert_called_once()
    # commit was called with explicit per-partition offsets, not coarse
    kwargs = consumer.commit.call_args.kwargs
    assert "offsets" in kwargs
    assert kwargs["offsets"]
    producer.send.assert_not_called()
    assert "t1" not in buffers
    assert "t1" not in retry_count


def test_flush_re_buffers_and_bumps_counter_on_failure():
    bundle = _bundle("t1", n=3)
    buffers = {"t1": bundle}
    last_seen = {"t1": 100.0}
    retry_count: dict[str, int] = {}
    tracker = _tracker_for("t1", offsets=(0, 1, 2))
    consumer = MagicMock()
    producer = MagicMock()

    with patch.object(kafka_worker.pipeline, "process", side_effect=RuntimeError("llm down")):
        kafka_worker._flush("t1", buffers, last_seen, retry_count, tracker, consumer, producer)

    consumer.commit.assert_not_called()
    producer.send.assert_not_called()
    assert buffers["t1"] == bundle
    assert retry_count["t1"] == 1


def test_flush_ships_to_dlq_after_exceeding_retry_budget_and_commits():
    bundle = _bundle("t1", n=3)
    buffers = {"t1": bundle}
    last_seen = {"t1": 100.0}
    retry_count = {"t1": KAFKA_MAX_BUNDLE_RETRIES}
    tracker = _tracker_for("t1", offsets=(0, 1, 2))
    consumer = MagicMock()
    producer = MagicMock()

    with patch.object(kafka_worker.pipeline, "process", side_effect=RuntimeError("llm down")):
        kafka_worker._flush("t1", buffers, last_seen, retry_count, tracker, consumer, producer)

    assert producer.send.call_count == len(bundle)
    for call in producer.send.call_args_list:
        assert call.args[0] == KAFKA_DLQ_TOPIC
    consumer.commit.assert_called_once()
    assert "t1" not in buffers
    assert "t1" not in retry_count


def test_flush_no_op_on_empty_bundle():
    buffers: dict = {}
    consumer = MagicMock()
    producer = MagicMock()

    kafka_worker._flush("t1", buffers, {}, {}, OffsetTracker(), consumer, producer)

    consumer.commit.assert_not_called()
    producer.send.assert_not_called()
