# debug-assistant

a small log-triage backend. ingests structured logs from kafka or http, correlates them by trace id within a sliding time window, and asks an llm for a one-line root-cause hypothesis per correlated bundle. results are persisted in postgres and exposed over a tiny api. prometheus metrics on the way in and out.

repo name is `go-debug-assistant` for historical reasons; the implementation is python.

## what this is

```
                                  +--------------+
   producers --> debug.logs  -->  | kafka_worker |  --+
   (any service)   topic          +--------------+    |
                                                      v
   POST /analyze (http) ----------------------+--->  pipeline
                                              |       |
                                              |       | 1. correlator: group by trace_id, expand each
                                              |       |    trace's window by +/- WINDOW_SECONDS,
                                              |       |    pull neighbour logs from the same window
                                              |       |
                                              |       | 2. llm: one azure openai call per bundle,
                                              |       |    timeout + retry on rate limits
                                              |       |
                                              |       v
                                              +---> postgres (analyses, raw_logs)
                                                      |
   GET /analysis/{trace_id}  <-----------------------+
   GET /metrics  -- prometheus counters + latency histogram
```

## stack

- python 3.12, fastapi, uvicorn
- postgres (psycopg2 + simple connection pool, schema migrations in `backend/migrations/`)
- kafka (kafka-python consumer in `backend/kafka_worker.py`)
- azure openai (single prompt, no agent framework)
- prometheus_client for metrics
- pytest for unit tests on the correlator

## what's NOT here (deliberate, called out so the readme doesn't lie)

- no react dashboard. previous version had a textarea + json dump; it didn't add anything over `curl /analyze | jq`. dropped.
- no multi-agent orchestration. previous version called three "agents" (root_cause / fix_suggester / impact) sequentially against the same log bundle. that's three llm calls for marginal extra signal. one prompt does the same job for 1/3 the cost and latency.
- no eval harness. there's no labeled dataset, no accuracy/precision claim. don't trust the llm output without one.
- no benchmark numbers. compose stack runs locally; throughput hasn't been measured under load. would need a k6/locust pass to claim a number.
- no auth, no rate limiting, no multi-tenant. single-deployment dev tool.

## run it

prerequisites: docker, docker compose, an azure openai resource (endpoint + key + deployment).

```bash
cp .env.example .env
# fill in AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT in .env
cd docker && docker compose up --build
# in another terminal, apply migrations:
docker compose exec api python -m backend.migrate
```

services:
- `postgres` — schema applied via `python -m backend.migrate`
- `kafka` + `zookeeper` — single broker for local dev
- `api` — fastapi on `:8000`
- `worker` — kafka consumer; idle until messages arrive on the `debug.logs` topic

quick check:
```bash
curl -s localhost:8000/healthz
curl -s localhost:8000/metrics | head
curl -s -X POST localhost:8000/analyze \
  -H 'content-type: application/json' \
  -d '{"logs":[{"timestamp":"2026-05-06T10:00:00Z","level":"ERROR","message":"db timeout","trace_id":"t1"}]}'
curl -s localhost:8000/analysis/t1
```

## kafka producer (sample)

```python
from kafka import KafkaProducer
import json

p = KafkaProducer(bootstrap_servers="localhost:29092", value_serializer=lambda v: json.dumps(v).encode())
p.send("debug.logs", {"timestamp": "2026-05-06T10:00:00Z", "level": "ERROR", "message": "db timeout", "trace_id": "t1"})
p.flush()
```

## run tests

```bash
pip install -r requirements.txt
pytest backend/tests
```

## layout

```
backend/
  api.py              fastapi app, /analyze + /analysis + /metrics + /healthz
  pipeline.py         correlate -> llm -> persist
  correlator.py       sliding-window trace correlation
  llm.py              one-call azure openai wrapper, retry on rate limits
  kafka_worker.py     standalone consumer process
  db.py               psycopg2 simple pool + helpers
  migrate.py          file-based migration runner
  metrics.py          prometheus counters + histograms
  config.py           env-only config (.env via python-dotenv)
  migrations/         versioned sql files
  tests/              pytest unit tests
docker/
  Dockerfile          built for both api and worker services
  docker-compose.yml  api + worker + postgres + kafka + zookeeper
```

## things i'd do next if i kept building this

- proper eval set: 50 hand-labeled trace bundles with known root causes, run nightly, track regression.
- otel tracing through pipeline (currently only structured logs + counters).
- replace single prompt with prompt versioning + a/b on each version.
- partition `analyses` by `created_at` once it gets big.
- circuit breaker around the llm call; fall back to template-based "no analysis" if azure is down.
- replace simple connection pool with a real one (asyncpg + sqlalchemy).
