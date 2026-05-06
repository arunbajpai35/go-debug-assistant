# api

interactive openapi docs are served at `http://localhost:8000/docs`. the static spec is committed at `openapi.json` and ci diffs against a regeneration on every push.

## endpoints

| method | path | description |
|---|---|---|
| GET  | `/healthz`            | liveness; always 200 if the process is up |
| GET  | `/readyz`             | readiness; pings postgres. 200 + `{"ok":true}` or 503 + `{"ok":false,"db":"down"}` |
| GET  | `/version`            | git_sha + build_date + app version (set at docker build time) |
| GET  | `/budget`             | current daily llm spend / limit / remaining |
| GET  | `/metrics`            | prometheus exposition format |
| POST | `/analyze`            | run a batch of logs through the pipeline (per-ip rate limited, max 5000 logs) |
| GET  | `/analysis/{trace_id}`| fetch the most recent persisted analysis for a trace |

## /analyze

```bash
curl -s -X POST localhost:8000/analyze \
  -H 'content-type: application/json' \
  -H 'x-request-id: my-rid-123' \
  -d '{
    "logs": [
      {"timestamp":"2026-05-06T10:00:00Z","level":"ERROR","message":"db timeout","trace_id":"t1"}
    ],
    "window_seconds": 60
  }'
```

response shape (one entry per correlated bundle):

```json
{
  "results": [
    {
      "trace_id": "t1",
      "log_text": "[2026-05-06T10:00:00Z] ERROR: db timeout",
      "analysis": "...",
      "model": "gpt-4.1-mini",
      "prompt_version": "v3",
      "category": "db",
      "root_cause": "...",
      "next_step": "...",
      "evidence": ["10:00:00"],
      "confidence": "high"
    }
  ],
  "count": 1
}
```

errors:

| code | reason |
|---|---|
| 422  | pydantic validation (empty `logs`, missing required fields) |
| 413  | over `MAX_LOGS_PER_REQUEST` |
| 429  | rate-limited; `retry-after` header indicates seconds |
| 500  | unhandled exception. response carries `request_id` for correlation |

## /analysis/{trace_id}

returns the most recent row for the trace, including the structured fields. 404 if no analysis has been persisted yet.

## headers

- **x-request-id** (request and response): a uuid is generated if the client doesn't set one. all log lines emitted during the request carry it; the 500 handler echoes it in the body.
