# debug-assistant

a small log-triage backend. ingests structured logs from kafka or http, correlates them by trace id within a sliding time window, and asks an llm for a one-line root-cause hypothesis per correlated bundle. results are persisted in postgres and exposed over a tiny api. prometheus metrics on the way in and out.

repo name is `go-debug-assistant` for historical reasons; the implementation is python.

## key properties

- **fully async hot path**: fastapi + sqlalchemy core async + asyncpg + AsyncAzureOpenAI
- **kafka ingestion** with per-partition offset tracking, dlq, retry counter, graceful shutdown
- **versioned prompts** (`v1`, `v2`, `v3`) with structured json output for v3
- **eval set** of 50 hand-labeled cases scored by keyword + embedding similarity vs gold answers
- **multi-replica safe** rate limit + budget cap (redis-backed when `REDIS_URL` is set)
- **circuit breaker** around the llm; **daily $ budget** that resets at utc midnight
- **partitioned `analyses` table** by month with monthly partitions auto-created from a cron-friendly script
- **otel tracing**, **structured json logs** with request_id propagation
- **multi-stage docker image** (~420 MB) running as non-root
- **ci**: ruff + mypy + pytest + integration with real postgres + openapi-fresh check + trivy scan

## quickstart

```bash
cp .env.example .env
# fill AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT
cd docker && docker compose up --build
docker compose exec api alembic upgrade head

curl -s localhost:8000/healthz
curl -s -X POST localhost:8000/analyze \
  -H 'content-type: application/json' \
  -d '{"logs":[{"timestamp":"2026-05-06T10:00:00Z","level":"ERROR","message":"db timeout","trace_id":"t1"}]}'
curl -s localhost:8000/analysis/t1
```

interactive docs at `/docs`. static spec committed at `openapi.json` (ci diffs against it on every push).
