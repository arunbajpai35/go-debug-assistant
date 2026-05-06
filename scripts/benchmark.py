"""measure throughput of the pieces of the pipeline that don't depend on external services.

we don't benchmark the llm call here — it's network-bound and rate-limited, so the number would say
more about azure than about this code. we benchmark:
  - log parsing + correlation (what the worker does between kafka receive and llm dispatch)
  - postgres persistence path (insert throughput against the local compose postgres)

usage:
    python scripts/benchmark.py                     # run all stages, default 10k events
    python scripts/benchmark.py --events 50000      # bigger sample
    python scripts/benchmark.py --skip-db           # correlator-only, no compose needed
"""
import argparse
import os
import random
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from backend import db, pipeline
from backend.correlator import correlate


def gen_logs(n: int, traces: int) -> list[dict]:
    base = datetime(2026, 5, 6, 10, tzinfo=UTC)
    trace_ids = [str(uuid.uuid4()) for _ in range(traces)]
    out = []
    for i in range(n):
        out.append(
            {
                "timestamp": (base + timedelta(milliseconds=i * 50)).isoformat().replace("+00:00", "Z"),
                "trace_id": random.choice(trace_ids),
                "level": random.choice(["INFO", "WARN", "ERROR"]),
                "message": f"event {i}",
            }
        )
    return out


def time_correlator(logs: list[dict], runs: int = 5) -> list[float]:
    durations = []
    for _ in range(runs):
        t0 = time.perf_counter()
        correlate(logs, window_seconds=60)
        durations.append(time.perf_counter() - t0)
    return durations


def time_persistence(events: int, runs: int = 3) -> list[float]:
    db.init_pool()
    durations = []
    for _ in range(runs):
        with db.conn() as c, c.cursor() as cur:
            cur.execute("delete from analyses where trace_id like 'bench-%'")
        t0 = time.perf_counter()
        for i in range(events):
            db.save_analysis(f"bench-{i}", "log text", f"analysis {i}", "bench")
        durations.append(time.perf_counter() - t0)
    return durations


def time_persistence_batched(events: int, runs: int = 3) -> list[float]:
    db.init_pool()
    rows = [(f"bench-{i}", "log text", f"analysis {i}", "bench") for i in range(events)]
    durations = []
    for _ in range(runs):
        with db.conn() as c, c.cursor() as cur:
            cur.execute("delete from analyses where trace_id like 'bench-%'")
        t0 = time.perf_counter()
        db.save_analyses_batch(rows)
        durations.append(time.perf_counter() - t0)
    return durations


def time_pipeline_stub_llm(logs: list[dict], runs: int = 3) -> list[float]:
    """end-to-end pipeline with the llm call stubbed (so we measure correlate + db,
    not network)."""
    db.init_pool()
    durations = []
    for _ in range(runs):
        with db.conn() as c, c.cursor() as cur:
            cur.execute("delete from analyses where trace_id like 'bench-%'")
        with patch("backend.pipeline.llm.analyze", return_value=("stub", "stub-model")):
            t0 = time.perf_counter()
            pipeline.process(logs, window_seconds=60)
            durations.append(time.perf_counter() - t0)
    return durations


def report(label: str, units: str, durations: list[float], events: int) -> None:
    mean = statistics.fmean(durations)
    p95 = sorted(durations)[max(int(len(durations) * 0.95) - 1, 0)]
    rate = events / mean if mean > 0 else float("inf")
    print(f"{label:<32} mean={mean*1000:.1f}ms p95={p95*1000:.1f}ms throughput={rate:,.0f} {units}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--events", type=int, default=10_000)
    p.add_argument("--traces", type=int, default=200)
    p.add_argument("--skip-db", action="store_true")
    args = p.parse_args()

    print(f"events={args.events:,} traces={args.traces}")
    print()

    logs = gen_logs(args.events, args.traces)

    print(f"warming jit on {args.events:,} events...")
    correlate(logs, window_seconds=60)

    cd = time_correlator(logs)
    report("correlate (in-memory)", "events/s", cd, args.events)

    if args.skip_db:
        return

    if not os.getenv("DB_HOST"):
        print()
        print("DB_HOST not set; skipping db benchmarks. start compose first or pass --skip-db.")
        return

    n = min(args.events, 1000)
    pd_ = time_persistence(n)
    report("save_analysis row-by-row", "rows/s", pd_, n)

    pdb = time_persistence_batched(args.events)
    report("save_analyses_batch", "rows/s", pdb, args.events)

    pld = time_pipeline_stub_llm(logs)
    report("pipeline (llm stubbed)", "events/s", pld, args.events)


if __name__ == "__main__":
    main()
