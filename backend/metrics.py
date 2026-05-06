from prometheus_client import Counter, Histogram

logs_ingested = Counter("logs_ingested_total", "raw logs ingested", ["source"])
windows_correlated = Counter("windows_correlated_total", "correlated windows produced")
llm_calls = Counter("llm_calls_total", "llm calls made", ["status"])
llm_latency = Histogram("llm_latency_seconds", "llm call latency", buckets=(0.5, 1, 2, 5, 10, 20, 30, 60))
analyses_persisted = Counter("analyses_persisted_total", "analyses written to postgres")
