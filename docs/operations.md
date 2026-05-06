# operations

## run locally

```bash
cp .env.example .env
# fill AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT
cd docker && docker compose up --build
docker compose exec api alembic upgrade head
```

services in the default stack:
- `postgres` (5433 → 5432, host port shifted to avoid conflicts with a local pg)
- `redis` (6379)
- `kafka` + `zookeeper`
- `api` on `:8000`
- `worker` runs `python -m backend.kafka_worker`

## observability stack (optional)

```bash
docker compose -f docker/docker-compose.yml -f docker/observability.yml up
```

adds:
- `otel-collector` (4317 grpc OTLP) — receives spans from api + worker; logs them to stderr by default. swap in jaeger / tempo by editing `docker/observability/otel-collector.yaml`.
- `prometheus` on `:9090` — scrapes the api's `/metrics`.
- `grafana` on `:3001` (anonymous viewer enabled, admin/admin) — datasource for prometheus auto-provisioned.

## migrations

```bash
docker compose exec api alembic upgrade head        # apply
docker compose exec api alembic current             # show current head
docker compose exec api alembic history             # list versions
```

new partitions for the `analyses` table:

```bash
docker compose exec api python scripts/create_analysis_partitions.py --months 6
```

idempotent (`if not exists`); run from cron monthly so partitions stay ahead of incoming data.

## env vars

see `.env.example` for the full list. essentials:

| var | default | notes |
|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | — | required for live llm calls |
| `AZURE_OPENAI_KEY` | — | required |
| `AZURE_OPENAI_DEPLOYMENT` | gpt-4o-mini | the deployment name in azure |
| `AZURE_OPENAI_EMBEDDING_DEPLOYMENT` | text-embedding-3-small | for eval embedding scoring |
| `PROMPT_VERSION` | v2 | switch to v3 for structured json output |
| `WINDOW_SECONDS` | 60 | sliding-window size for trace correlation |
| `MAX_LOGS_PER_REQUEST` | 5000 | `/analyze` size cap |
| `RATE_LIMIT_PER_MINUTE` | 30 | per-ip rate limit on `/analyze` |
| `LLM_DAILY_BUDGET_USD` | 5.0 | daily $ cap; resets at utc midnight |
| `LLM_CB_FAILURE_THRESHOLD` | 5 | circuit breaker trip count |
| `LLM_CB_COOLDOWN_SECONDS` | 30 | cooldown before half_open |
| `KAFKA_BROKERS` | localhost:9092 | comma-separated |
| `KAFKA_TOPIC` | debug.logs | input topic |
| `KAFKA_DLQ_TOPIC` | debug.logs.dlq | dead-letter topic |
| `KAFKA_BATCH_MAX` | 200 | flush a trace bundle when it reaches this size |
| `KAFKA_FLUSH_IDLE_SECONDS` | 60 | flush a trace bundle that's been idle this long |
| `KAFKA_MAX_BUNDLE_RETRIES` | 3 | dlq after this many failed flushes |
| `REDIS_URL` | (empty) | set to `redis://host:port/db` for multi-replica safety |
| `CORS_ORIGINS` | http://localhost:3000 | comma-separated |
| `CORS_ALLOW_METHODS` | GET,POST,OPTIONS | explicit, no wildcards |
| `LOG_FORMAT` | json | set to `text` for local debugging |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (empty) | grpc endpoint of an otel collector |
| `OTEL_CONSOLE` | (empty) | set to `1` to print spans to stdout |

## sample producer

```bash
python scripts/produce_sample.py --traces 3 --count 10
docker compose -f docker/docker-compose.yml logs -f worker
```

## benchmark

```bash
PYTHONPATH=. DB_HOST=localhost DB_PORT=5433 python scripts/benchmark.py --events 20000 --traces 200
```

## ci

four jobs, all required to pass:

- `unit` — ruff + mypy + pytest (~105 unit tests)
- `integration` — pytest against a postgres service container
- `openapi-fresh` — regenerates `openapi.json` and diffs vs the committed file
- `image-scan` — trivy on the runtime image, severity HIGH,CRITICAL, fails on findings

## docs site

```bash
pip install mkdocs mkdocs-material
mkdocs serve     # http://localhost:8000
mkdocs build     # static site in site/
```
