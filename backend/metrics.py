from prometheus_client import Counter, Gauge, Histogram

logs_ingested = Counter("logs_ingested_total", "raw logs ingested", ["source"])
windows_correlated = Counter("windows_correlated_total", "correlated windows produced")
llm_calls = Counter("llm_calls_total", "llm calls made", ["status"])
llm_latency = Histogram("llm_latency_seconds", "llm call latency", buckets=(0.5, 1, 2, 5, 10, 20, 30, 60))
analyses_persisted = Counter("analyses_persisted_total", "analyses written to postgres")

bundle_retries = Counter("bundle_retries_total", "bundle re-flush attempts after a failure")
bundles_dlq = Counter("bundles_dlq_total", "bundles shipped to dead-letter topic after exceeding retry budget")
worker_buffers = Gauge("worker_buffers", "number of trace_id buffers held by the kafka worker")
llm_circuit_state = Gauge(
    "llm_circuit_state",
    "current llm circuit breaker state (0=closed, 1=half_open, 2=open)",
)
