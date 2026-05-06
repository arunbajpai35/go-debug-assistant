import logging
import time

from openai import APIError, AzureOpenAI, RateLimitError

from backend import metrics as m
from backend.budget import budget
from backend.circuit_breaker import CircuitBreaker, State
from backend.config import (
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    LLM_CB_COOLDOWN_SECONDS,
    LLM_CB_FAILURE_THRESHOLD,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
    PROMPT_VERSION,
)
from backend.prompts import get as get_prompt

log = logging.getLogger(__name__)


breaker = CircuitBreaker(
    failure_threshold=LLM_CB_FAILURE_THRESHOLD,
    cooldown_seconds=LLM_CB_COOLDOWN_SECONDS,
    name="llm",
)


_STATE_VALUE = {State.CLOSED: 0, State.HALF_OPEN: 1, State.OPEN: 2}


def _publish_state() -> None:
    m.llm_circuit_state.set(_STATE_VALUE[breaker.state])


_client: AzureOpenAI | None = None


def client() -> AzureOpenAI:
    global _client
    if _client is None:
        if not AZURE_OPENAI_KEY or not AZURE_OPENAI_ENDPOINT:
            raise RuntimeError("azure openai not configured (AZURE_OPENAI_KEY / AZURE_OPENAI_ENDPOINT)")
        _client = AzureOpenAI(
            api_key=AZURE_OPENAI_KEY,
            api_version=AZURE_OPENAI_API_VERSION,
            azure_endpoint=AZURE_OPENAI_ENDPOINT,
            timeout=LLM_TIMEOUT_SECONDS,
            max_retries=0,
        )
    return _client


def analyze(log_text: str, window_seconds: int, version: str | None = None) -> tuple[str, str, str]:
    """returns (analysis_text, model_name, prompt_version).
    raises BudgetExceeded if today's estimated spend already meets the daily limit.
    raises CircuitOpen if the breaker is currently open after repeated failures.
    retries rate limits / 5xx within a single call; the breaker tracks call-level success/failure."""
    budget.check()
    breaker.before_call()
    _publish_state()

    v = version or PROMPT_VERSION
    system, user_template = get_prompt(v)
    user_msg = user_template.format(window=window_seconds, log_text=log_text)

    last_err: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            resp = client().chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            usage = resp.usage
            if usage is not None:
                spent = budget.record(
                    AZURE_OPENAI_DEPLOYMENT,
                    usage.prompt_tokens or 0,
                    usage.completion_tokens or 0,
                )
                log.info(
                    "llm call ok",
                    extra={
                        "prompt_version": v,
                        "model": AZURE_OPENAI_DEPLOYMENT,
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "budget_spent_usd": round(spent, 6),
                    },
                )
            content = resp.choices[0].message.content or ""
            breaker.on_success()
            _publish_state()
            return content.strip(), AZURE_OPENAI_DEPLOYMENT, v
        except RateLimitError as e:
            last_err = e
            wait = 2**attempt
            log.warning("llm rate-limited, retrying in %ss attempt=%d", wait, attempt + 1)
            time.sleep(wait)
        except APIError as e:
            last_err = e
            log.exception("llm api error attempt=%d", attempt + 1)
            if attempt == LLM_MAX_RETRIES:
                break
            time.sleep(1)

    breaker.on_failure()
    _publish_state()
    raise RuntimeError(f"llm call failed after {LLM_MAX_RETRIES + 1} attempts: {last_err}")
