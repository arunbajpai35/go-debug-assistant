"""thin wrapper around azure openai embeddings with a per-process in-memory cache.

embeddings are deterministic for a (model, text) pair, so caching avoids re-billing for the
gold answers on every eval run. for cross-run caching, the eval runner persists a sidecar
file — see eval/run_eval.py."""
import logging
import math

from openai import AzureOpenAI

from backend.config import (
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    LLM_TIMEOUT_SECONDS,
)

log = logging.getLogger(__name__)

_client: AzureOpenAI | None = None
_cache: dict[tuple[str, str], list[float]] = {}


def _client_lazy() -> AzureOpenAI:
    global _client
    if _client is None:
        if not AZURE_OPENAI_KEY or not AZURE_OPENAI_ENDPOINT:
            raise RuntimeError("azure openai not configured (AZURE_OPENAI_KEY / AZURE_OPENAI_ENDPOINT)")
        _client = AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=2,
        )
    return _client


def embed(text: str, model: str | None = None) -> list[float]:
    deployment = model or AZURE_OPENAI_EMBEDDING_DEPLOYMENT
    key = (deployment, text)
    cached = _cache.get(key)
    if cached is not None:
        return cached
    resp = _client_lazy().embeddings.create(model=deployment, input=text)
    vec = resp.data[0].embedding
    _cache[key] = vec
    return vec


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def reset_cache() -> None:
    _cache.clear()
