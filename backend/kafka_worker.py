"""standalone kafka consumer.

reads json log records off `KAFKA_TOPIC`, buffers them per trace_id, and flushes a bundle to the
pipeline whenever:
  - the per-trace buffer reaches `KAFKA_BATCH_MAX` entries, or
  - the buffer has been idle for `KAFKA_FLUSH_IDLE_SECONDS`.

reliability:
  - manual offset commit, **per-partition precise**. each message is registered with its
    (topic, partition, offset) in OffsetTracker; only the earliest-still-unprocessed offset per
    partition is committed. a hard kill mid-buffer redelivers exactly the unprocessed traces,
    not the already-flushed ones.
  - on flush failure: the bundle is re-buffered and a retry counter bumped. offsets stay
    in-flight so we don't commit past them.
  - after `KAFKA_MAX_BUNDLE_RETRIES` failed flushes for the same trace_id, the bundle is shipped
    to `KAFKA_DLQ_TOPIC`, the trace's offsets are completed, and the per-partition watermark
    advances normally.
  - sigint/sigterm flips a flag; the main loop drains remaining buffers, then exits."""
import json
import logging
import signal
import time
from collections import defaultdict

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable

from backend import db, log_setup, metrics, pipeline, tracing
from backend.config import (
    KAFKA_BATCH_MAX,
    KAFKA_BROKERS,
    KAFKA_DLQ_TOPIC,
    KAFKA_FLUSH_IDLE_SECONDS,
    KAFKA_GROUP,
    KAFKA_MAX_BUNDLE_RETRIES,
    KAFKA_TOPIC,
    WINDOW_SECONDS,
)
from backend.kafka_offsets import OffsetTracker

tracing.init(service_name="debug-assistant-worker")

log = logging.getLogger(__name__)


_running = True


def _stop(*_args) -> None:
    global _running
    _running = False
    log.info("shutdown signal received; will exit after current flush")


def _make_consumer() -> KafkaConsumer:
    return KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKERS.split(","),
        group_id=KAFKA_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="latest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        consumer_timeout_ms=1000,
    )


def _make_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BROKERS.split(","),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
    )


def consume() -> None:
    db.init_pool()
    consumer = _make_consumer()
    producer = _make_producer()
    tracker = OffsetTracker()
    log.info(
        "kafka worker started topic=%s dlq=%s group=%s batch_max=%d idle_s=%d max_retries=%d",
        KAFKA_TOPIC,
        KAFKA_DLQ_TOPIC,
        KAFKA_GROUP,
        KAFKA_BATCH_MAX,
        KAFKA_FLUSH_IDLE_SECONDS,
        KAFKA_MAX_BUNDLE_RETRIES,
    )

    buffers: dict[str, list[dict]] = defaultdict(list)
    last_seen: dict[str, float] = {}
    retry_count: dict[str, int] = {}

    try:
        while _running:
            for msg in consumer:
                if not _running:
                    break
                entry = msg.value
                trace_id = entry.get("trace_id") if isinstance(entry, dict) else None
                if not trace_id:
                    log.warning("dropping message without trace_id offset=%s", msg.offset)
                    continue
                buffers[trace_id].append(entry)
                last_seen[trace_id] = time.time()
                tracker.add(msg.topic, msg.partition, msg.offset, trace_id)
                metrics.logs_ingested.labels(source="kafka").inc()
                metrics.worker_buffers.set(len(buffers))
                if len(buffers[trace_id]) >= KAFKA_BATCH_MAX:
                    log.info("flushing trace_id=%s reason=batch_full size=%d", trace_id, len(buffers[trace_id]))
                    _flush(trace_id, buffers, last_seen, retry_count, tracker, consumer, producer)

            now = time.time()
            for trace_id in list(buffers.keys()):
                if now - last_seen.get(trace_id, now) >= KAFKA_FLUSH_IDLE_SECONDS:
                    log.info("flushing trace_id=%s reason=idle size=%d", trace_id, len(buffers[trace_id]))
                    _flush(trace_id, buffers, last_seen, retry_count, tracker, consumer, producer)

        log.info("draining %d remaining buffer(s) before exit", len(buffers))
        for trace_id in list(buffers.keys()):
            _flush(trace_id, buffers, last_seen, retry_count, tracker, consumer, producer)

    finally:
        producer.flush()
        producer.close()
        consumer.close()
        db.close_pool()


def _flush(
    trace_id: str,
    buffers: dict,
    last_seen: dict,
    retry_count: dict,
    tracker: OffsetTracker,
    consumer: KafkaConsumer,
    producer: KafkaProducer,
) -> None:
    bundle = buffers.pop(trace_id, [])
    last_seen.pop(trace_id, None)
    metrics.worker_buffers.set(len(buffers))
    if not bundle:
        return
    try:
        pipeline.process(bundle, window_seconds=WINDOW_SECONDS)
        commits = tracker.complete(trace_id)
        if commits:
            consumer.commit(offsets=commits)
        retry_count.pop(trace_id, None)
        return
    except Exception:
        log.exception("flush failed trace_id=%s", trace_id)

    attempt = retry_count.get(trace_id, 0) + 1
    if attempt > KAFKA_MAX_BUNDLE_RETRIES:
        for entry in bundle:
            producer.send(KAFKA_DLQ_TOPIC, entry)
        producer.flush()
        commits = tracker.complete(trace_id)
        if commits:
            consumer.commit(offsets=commits)
        retry_count.pop(trace_id, None)
        metrics.bundles_dlq.inc()
        log.error("dlq trace_id=%s after %d attempts size=%d", trace_id, attempt - 1, len(bundle))
        return

    retry_count[trace_id] = attempt
    buffers[trace_id] = bundle
    last_seen[trace_id] = time.time() - KAFKA_FLUSH_IDLE_SECONDS  # eligible for next idle pass
    metrics.bundle_retries.inc()
    metrics.worker_buffers.set(len(buffers))
    log.warning("retry trace_id=%s attempt=%d/%d", trace_id, attempt, KAFKA_MAX_BUNDLE_RETRIES)


def main() -> None:
    log_setup.configure()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    while _running:
        try:
            consume()
            return
        except NoBrokersAvailable:
            log.warning("kafka not reachable, retrying in 5s")
            time.sleep(5)


if __name__ == "__main__":
    main()
