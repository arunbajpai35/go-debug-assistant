import os

from dotenv import load_dotenv

load_dotenv()


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"missing required env var: {key}")
    return val or ""


AZURE_OPENAI_ENDPOINT = _env("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_KEY = _env("AZURE_OPENAI_KEY")
AZURE_OPENAI_API_VERSION = _env("AZURE_OPENAI_API_VERSION", "2024-02-01")
AZURE_OPENAI_DEPLOYMENT = _env("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

DB_HOST = _env("DB_HOST", "localhost")
DB_PORT = int(_env("DB_PORT", "5432"))
DB_USER = _env("DB_USER", "postgres")
DB_PASSWORD = _env("DB_PASSWORD", "postgres")
DB_NAME = _env("DB_NAME", "debug_logs")

KAFKA_BROKERS = _env("KAFKA_BROKERS", "localhost:9092")
KAFKA_TOPIC = _env("KAFKA_TOPIC", "debug.logs")
KAFKA_DLQ_TOPIC = _env("KAFKA_DLQ_TOPIC", "debug.logs.dlq")
KAFKA_GROUP = _env("KAFKA_GROUP", "debug-assistant")
KAFKA_BATCH_MAX = int(_env("KAFKA_BATCH_MAX", "200"))
KAFKA_FLUSH_IDLE_SECONDS = int(_env("KAFKA_FLUSH_IDLE_SECONDS", "60"))
KAFKA_MAX_BUNDLE_RETRIES = int(_env("KAFKA_MAX_BUNDLE_RETRIES", "3"))

CORS_ORIGINS = [o.strip() for o in _env("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

WINDOW_SECONDS = int(_env("WINDOW_SECONDS", "60"))
MAX_LOGS_PER_REQUEST = int(_env("MAX_LOGS_PER_REQUEST", "5000"))
LLM_TIMEOUT_SECONDS = int(_env("LLM_TIMEOUT_SECONDS", "30"))
LLM_MAX_RETRIES = int(_env("LLM_MAX_RETRIES", "2"))
PROMPT_VERSION = _env("PROMPT_VERSION", "v2")

# safety knobs
RATE_LIMIT_PER_MINUTE = int(_env("RATE_LIMIT_PER_MINUTE", "30"))
LLM_DAILY_BUDGET_USD = float(_env("LLM_DAILY_BUDGET_USD", "5.0"))

# circuit breaker: trip after N consecutive failures, cool down for X seconds
LLM_CB_FAILURE_THRESHOLD = int(_env("LLM_CB_FAILURE_THRESHOLD", "5"))
LLM_CB_COOLDOWN_SECONDS = float(_env("LLM_CB_COOLDOWN_SECONDS", "30"))
