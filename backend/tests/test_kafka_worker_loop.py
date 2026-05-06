"""tests for the kafka_worker.consume() main loop. mocks the kafka consumer + producer + db
so the loop terminates after a controlled message stream."""
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

from kafka.errors import NoBrokersAvailable

from backend import kafka_worker


class _FakeMessage:
    def __init__(self, value: dict, offset: int = 0, partition: int = 0, topic: str = "debug.logs") -> None:
        self.value = value
        self.offset = offset
        self.partition = partition
        self.topic = topic


class _FakeConsumer:
    """yields messages from a queue, then a single empty pass to trigger the idle phase, then
    sets the worker's _running flag to False so consume() exits."""

    def __init__(self, messages: list[_FakeMessage]) -> None:
        self._batches = [messages, []]
        self._stop_after = len(self._batches)
        self._iter_count = 0
        self.commit = MagicMock()
        self.close = MagicMock()

    def __iter__(self) -> Iterator[_FakeMessage]:
        if self._iter_count >= self._stop_after:
            kafka_worker._running = False
            return iter([])
        batch = self._batches[self._iter_count]
        self._iter_count += 1
        if self._iter_count >= self._stop_after:
            kafka_worker._running = False
        return iter(batch)


def _msg(trace_id: str, offset: int = 0) -> _FakeMessage:
    return _FakeMessage(
        value={
            "timestamp": "2026-05-06T10:00:00Z",
            "level": "ERROR",
            "message": "boom",
            "trace_id": trace_id,
        },
        offset=offset,
    )


def _setup_module_patches():
    """patches that every consume() test needs. returns a tuple of mocks."""
    consumer = _FakeConsumer([_msg("t1", 0), _msg("t1", 1)])
    producer = MagicMock()
    init_pool = MagicMock()
    close_pool = AsyncMock()
    process = AsyncMock(return_value=[])
    return consumer, producer, init_pool, close_pool, process


def test_consume_initializes_db_processes_messages_and_cleans_up():
    kafka_worker._running = True
    consumer, producer, init_pool, close_pool, process = _setup_module_patches()

    with (
        patch("backend.kafka_worker._make_consumer", return_value=consumer),
        patch("backend.kafka_worker._make_producer", return_value=producer),
        patch("backend.kafka_worker.db.init_pool", init_pool),
        patch("backend.kafka_worker.db.close_pool", close_pool),
        patch("backend.kafka_worker.pipeline.process", process),
        patch("backend.kafka_worker.KAFKA_BATCH_MAX", 1),  # flush immediately on each message
    ):
        kafka_worker.consume()

    init_pool.assert_called_once()
    assert process.await_count == 2
    consumer.close.assert_called_once()
    producer.flush.assert_called_once()
    producer.close.assert_called_once()


def test_consume_drops_messages_without_trace_id():
    kafka_worker._running = True
    bad = _FakeMessage(value={"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "no trace"})
    good = _msg("t1", offset=0)
    consumer = _FakeConsumer([bad, good])
    producer = MagicMock()
    process = AsyncMock(return_value=[])

    with (
        patch("backend.kafka_worker._make_consumer", return_value=consumer),
        patch("backend.kafka_worker._make_producer", return_value=producer),
        patch("backend.kafka_worker.db.init_pool"),
        patch("backend.kafka_worker.db.close_pool", AsyncMock()),
        patch("backend.kafka_worker.pipeline.process", process),
        patch("backend.kafka_worker.KAFKA_BATCH_MAX", 1),
    ):
        kafka_worker.consume()

    # only the good message should have been processed
    assert process.await_count == 1


def test_main_retries_when_brokers_unreachable_then_exits_cleanly():
    kafka_worker._running = True
    call_count = {"n": 0}

    def fail_then_stop():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise NoBrokersAvailable()
        kafka_worker._running = False

    with (
        patch("backend.kafka_worker.consume", side_effect=fail_then_stop),
        patch("backend.kafka_worker.time.sleep"),  # don't actually wait 5s
        patch("backend.kafka_worker.log_setup.configure"),
        patch("backend.kafka_worker.signal.signal"),
    ):
        kafka_worker.main()

    assert call_count["n"] == 2
