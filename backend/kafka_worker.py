"""standalone kafka consumer.

reads json log records off `KAFKA_TOPIC`, buffers them per trace_id, and flushes a bundle to the
pipeline whenever (a) the per-trace buffer is older than `WINDOW_SECONDS` or (b) the trace has
accumulated `BATCH_MAX` entries.
"""
import json
import logging
import signal
import time
from collections import defaultdict

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from backend import db, metrics, pipeline
from backend.config import KAFKA_BROKERS, KAFKA_GROUP, KAFKA_TOPIC, WINDOW_SECONDS

log = logging.getLogger(__name__)

BATCH_MAX = 200
FLUSH_IDLE_SECONDS = WINDOW_SECONDS


_running = True


def _stop(*_args) -> None:
    global _running
    _running = False
    log.info("shutdown signal received")


def consume() -> None:
    db.init_pool()
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BROKERS.split(","),
        group_id=KAFKA_GROUP,
        enable_auto_commit=False,
        auto_offset_reset="latest",
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        consumer_timeout_ms=1000,
    )
    log.info("kafka consumer started topic=%s group=%s", KAFKA_TOPIC, KAFKA_GROUP)

    buffers: dict[str, list[dict]] = defaultdict(list)
    last_seen: dict[str, float] = {}

    while _running:
        for msg in consumer:
            entry = msg.value
            trace_id = entry.get("trace_id")
            if not trace_id:
                continue
            buffers[trace_id].append(entry)
            last_seen[trace_id] = time.time()
            metrics.logs_ingested.labels(source="kafka").inc()
            log.debug("buffered trace_id=%s size=%d", trace_id, len(buffers[trace_id]))
            if len(buffers[trace_id]) >= BATCH_MAX:
                log.info("flushing trace_id=%s reason=batch_full size=%d", trace_id, len(buffers[trace_id]))
                _flush(trace_id, buffers, last_seen, consumer)

        now = time.time()
        for trace_id in list(buffers.keys()):
            if now - last_seen.get(trace_id, now) >= FLUSH_IDLE_SECONDS:
                log.info("flushing trace_id=%s reason=idle size=%d", trace_id, len(buffers[trace_id]))
                _flush(trace_id, buffers, last_seen, consumer)

    consumer.close()
    db.close_pool()


def _flush(trace_id: str, buffers: dict, last_seen: dict, consumer: KafkaConsumer) -> None:
    bundle = buffers.pop(trace_id, [])
    last_seen.pop(trace_id, None)
    if not bundle:
        return
    try:
        pipeline.process(bundle, window_seconds=WINDOW_SECONDS)
        consumer.commit()
    except Exception:
        log.exception("flush failed trace_id=%s", trace_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
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
