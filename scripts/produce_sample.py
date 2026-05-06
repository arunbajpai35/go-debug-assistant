"""publish a small batch of synthetic logs to the kafka topic so a reviewer can exercise the worker path.

usage:
    python scripts/produce_sample.py [--brokers HOST:PORT] [--topic NAME] [--count N]

env var fallbacks: KAFKA_BROKERS, KAFKA_TOPIC.
"""
import argparse
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

from kafka import KafkaProducer

DEFAULT_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:29092")
DEFAULT_TOPIC = os.getenv("KAFKA_TOPIC", "debug.logs")

LEVELS = ["INFO", "WARN", "ERROR"]
TEMPLATES = [
    "db connection timeout after {ms}ms",
    "request to upstream {svc} failed: {code}",
    "cache miss for key user:{uid}",
    "rate limit exceeded for tenant {tid}",
    "unhandled exception in handler {handler}",
]


def synthetic_log(trace_id: str) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": random.choice(LEVELS),
        "trace_id": trace_id,
        "message": random.choice(TEMPLATES).format(
            ms=random.randint(100, 5000),
            svc=random.choice(["payments", "search", "auth"]),
            code=random.choice([500, 502, 504]),
            uid=random.randint(1, 10000),
            tid=random.randint(1, 50),
            handler=random.choice(["create_user", "checkout", "search_query"]),
        ),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--brokers", default=DEFAULT_BROKERS)
    p.add_argument("--topic", default=DEFAULT_TOPIC)
    p.add_argument("--count", type=int, default=10, help="logs per trace")
    p.add_argument("--traces", type=int, default=3, help="number of distinct trace_ids")
    args = p.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=args.brokers.split(","),
        value_serializer=lambda v: json.dumps(v).encode(),
    )
    sent = 0
    for _ in range(args.traces):
        trace_id = str(uuid.uuid4())
        for _ in range(args.count):
            producer.send(args.topic, synthetic_log(trace_id))
            sent += 1
            time.sleep(0.05)
    producer.flush()
    producer.close()
    print(f"sent {sent} logs across {args.traces} traces to topic={args.topic}")


if __name__ == "__main__":
    main()
