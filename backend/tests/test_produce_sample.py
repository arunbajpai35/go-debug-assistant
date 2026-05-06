"""tests for the synthetic log generator + the producer wiring (kafka client mocked)."""
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch


def test_synthetic_log_has_required_fields():
    from scripts.produce_sample import synthetic_log

    out = synthetic_log("trace-xyz")
    assert out["trace_id"] == "trace-xyz"
    assert out["level"] in {"INFO", "WARN", "ERROR"}
    assert out["timestamp"].endswith("Z")
    # round-trip parses as iso (with the Z suffix replaced)
    datetime.fromisoformat(out["timestamp"].replace("Z", "+00:00"))
    assert isinstance(out["message"], str) and len(out["message"]) > 0


def test_synthetic_log_message_uses_a_known_template():
    from scripts.produce_sample import TEMPLATES, synthetic_log

    out = synthetic_log("t1")
    # at least one of the template stems should be a substring of the formatted message
    stems = ["timeout", "upstream", "cache miss", "rate limit", "unhandled exception"]
    assert any(stem in out["message"] for stem in stems), out["message"]
    # sanity: TEMPLATES non-empty (would silently break the generator)
    assert len(TEMPLATES) >= 5


def test_synthetic_log_timestamp_is_utc_now_within_a_few_seconds():
    from scripts.produce_sample import synthetic_log

    before = datetime.now(UTC)
    out = synthetic_log("t1")
    parsed = datetime.fromisoformat(out["timestamp"].replace("Z", "+00:00"))
    after = datetime.now(UTC)
    assert before <= parsed <= after


def test_main_sends_count_per_trace_and_flushes():
    """produce_sample.main wires KafkaProducer + a 3x10 default; mock the producer and verify
    the right number of sends + a single flush."""
    fake_producer = MagicMock()
    with (
        patch("scripts.produce_sample.KafkaProducer", return_value=fake_producer),
        patch("scripts.produce_sample.time.sleep"),  # don't wait between sends
        patch("sys.argv", ["produce_sample", "--traces", "2", "--count", "3"]),
    ):
        from scripts.produce_sample import main

        main()

    assert fake_producer.send.call_count == 2 * 3
    fake_producer.flush.assert_called_once()
    fake_producer.close.assert_called_once()


def test_main_distributes_messages_across_distinct_trace_ids():
    fake_producer = MagicMock()
    with (
        patch("scripts.produce_sample.KafkaProducer", return_value=fake_producer),
        patch("scripts.produce_sample.time.sleep"),
        patch("sys.argv", ["produce_sample", "--traces", "3", "--count", "2"]),
    ):
        from scripts.produce_sample import main

        main()

    payloads = [call.args[1] for call in fake_producer.send.call_args_list]
    trace_ids = {p["trace_id"] for p in payloads}
    assert len(trace_ids) == 3
    # 2 messages per trace
    for tid in trace_ids:
        assert sum(1 for p in payloads if p["trace_id"] == tid) == 2
