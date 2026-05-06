# debug-assistant

[![ci](https://github.com/arunbajpai35/go-debug-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/arunbajpai35/go-debug-assistant/actions/workflows/ci.yml)

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

## measured throughput

bench machine: m2 mac, single-process, postgres in local docker. produced with `PYTHONPATH=. python scripts/benchmark.py --events 20000 --traces 200` against the compose stack.

| stage                          | throughput        |
|--------------------------------|-------------------|
| correlate (in-memory)          | ~30,000 events/s  |
| save_analysis row-by-row       | ~2,500 rows/s     |
| save_analyses_batch            | ~177,000 rows/s   |
| pipeline (llm stubbed)         | ~5,000 events/s   |

(`save_analyses_batch` uses `psycopg2.extras.execute_values`. the pipeline uses it; the row-by-row figure is kept as a comparison for the pr that switched it.)

these are dev-machine numbers, single-process, no batching of inserts. don't read them as production capacity. they exist so claims in this readme are checkable, not vibes.

llm latency is excluded on purpose — that number reports azure's behaviour, not this code's.

## eval

25 hand-labeled trace bundles in `eval/dataset.json`, scored by keyword + anti-keyword hit rate. small enough to be honest about: this is a smoke test for prompt regressions, not a benchmark. see `eval/README.md`.

```bash
python -m eval.run_eval --version v2       # default version, writes eval/results-v2.json
python -m eval.run_eval --version v1
python -m eval.compare eval/results-v1.json eval/results-v2.json
```

prompts are versioned (`backend/prompts/v{N}.py`); `PROMPT_VERSION` env switches the live system. each persisted analysis records which version produced it (`analyses.prompt_version` column).

## safety knobs

- **per-ip sliding-window rate limit** on `/analyze`. `RATE_LIMIT_PER_MINUTE` env (default 30). 429 responses include a `retry-after` header. in-memory only — replace with redis-backed limiter for multi-replica deployments.
- **daily llm $ budget cap**: `LLM_DAILY_BUDGET_USD` env (default 5.0). estimated from openai usage tokens × per-model price table; resets at utc midnight. once exceeded, `llm.analyze` raises `BudgetExceeded` and the pipeline records the bundle as failed instead of calling azure. `GET /budget` exposes current spend / remaining.
- **circuit breaker** around the llm call. trips after `LLM_CB_FAILURE_THRESHOLD` consecutive failures (default 5), refuses calls for `LLM_CB_COOLDOWN_SECONDS` (default 30s), then allows one trial in `half_open`. exposed as the `llm_circuit_state` prometheus gauge (0=closed, 1=half_open, 2=open).

both are guard rails, not invoices. real cost lives on azure's bill.

## tracing

opentelemetry spans around `pipeline.process` → `correlate` → `llm.analyze` → `db.save_analysis`. fastapi + psycopg2 are auto-instrumented.

```bash
# console export for local debugging
OTEL_CONSOLE=true docker compose -f docker/docker-compose.yml up

# OTLP export (jaeger, tempo, datadog agent, etc.)
OTEL_EXPORTER_OTLP_ENDPOINT=http://collector:4317 docker compose ...
```

## what's NOT here (deliberate, called out so the readme doesn't lie)

- no react dashboard. previous version had a textarea + json dump; it didn't add anything over `curl /analyze | jq`. dropped.
- no multi-agent orchestration. previous version called three "agents" (root_cause / fix_suggester / impact) sequentially against the same log bundle. that's three llm calls for marginal extra signal. one prompt does the same job for 1/3 the cost and latency.
- the eval set has 10 cases. that's enough to spot regressions, not enough to claim accuracy.
- no auth, no multi-tenant. single-deployment dev tool. (per-ip rate limit + daily llm $ budget cap *are* in place — see below.)
- the kafka worker has no dlq for poison messages yet — repeatedly-failing bundles loop. on the punchlist.

## run it

prerequisites: docker, docker compose, an azure openai resource (endpoint + key + deployment).

```bash
cp .env.example .env
# fill in AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT in .env
cd docker && docker compose up --build
# in another terminal, apply migrations:
docker compose exec api alembic upgrade head
```

services:
- `postgres` — schema applied via `python -m backend.migrate`
- `kafka` + `zookeeper` — single broker for local dev
- `api` — fastapi on `:8000`
- `worker` — kafka consumer; idle until messages arrive on the `debug.logs` topic

quick check:
```bash
curl -s localhost:8000/healthz
curl -s localhost:8000/readyz
curl -s localhost:8000/metrics | head
curl -s -X POST localhost:8000/analyze \
  -H 'content-type: application/json' \
  -d '{"logs":[{"timestamp":"2026-05-06T10:00:00Z","level":"ERROR","message":"db timeout","trace_id":"t1"}]}'
curl -s localhost:8000/analysis/t1
```

interactive openapi docs at `http://localhost:8000/docs`.

## try the kafka path

```bash
python scripts/produce_sample.py --traces 3 --count 10
# worker picks up messages, buffers per trace, flushes when idle for WINDOW_SECONDS
docker compose -f docker/docker-compose.yml logs -f worker
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
  alembic/            alembic migrations (`alembic upgrade head`)
  metrics.py          prometheus counters + histograms
  config.py           env-only config (.env via python-dotenv)
  tests/              pytest unit tests
docker/
  Dockerfile          built for both api and worker services
  docker-compose.yml  api + worker + postgres + kafka + zookeeper
```

## things i'd do next if i kept building this

- expand eval set to 50+ cases; switch from keyword scoring to embedding-similarity vs gold answers.
- prompt versioning + side-by-side a/b runs against the eval set per version.
- circuit breaker around the llm call; fall back to template-based "no analysis" if azure is down.
- partition `analyses` by `created_at` once it gets big.
- replace simple connection pool with asyncpg + sqlalchemy core.
