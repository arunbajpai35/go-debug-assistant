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
from backend.llm_schema import AnalysisResult, parse_v2_text, parse_v3_json
from backend.prompts import STRUCTURED_VERSIONS
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


def _enrich(result: AnalysisResult) -> AnalysisResult:
    """fill structured fields from the raw text best-effort, based on prompt version."""
    if result.prompt_version in STRUCTURED_VERSIONS:
        parsed = parse_v3_json(result.raw_text)
    elif result.prompt_version == "v2":
        parsed = parse_v2_text(result.raw_text)
    else:
        return result

    if isinstance(parsed.get("category"), str):
        result.category = parsed["category"].strip().lower()
    if isinstance(parsed.get("root_cause"), str):
        result.root_cause = parsed["root_cause"].strip()
    if isinstance(parsed.get("next_step"), str):
        result.next_step = parsed["next_step"].strip()
    if isinstance(parsed.get("evidence"), list):
        result.evidence = [str(x) for x in parsed["evidence"]]
    elif isinstance(parsed.get("evidence"), str):
        result.evidence = [v.strip() for v in parsed["evidence"].split(",") if v.strip()]
    if isinstance(parsed.get("confidence"), str):
        result.confidence = parsed["confidence"].strip().lower()
    return result


def analyze(
    log_text: str,
    window_seconds: int,
    version: str | None = None,
    seed: int | None = None,
    temperature: float = 0.2,
) -> AnalysisResult:
    """returns an AnalysisResult with raw_text always populated. structured fields
    (category / root_cause / next_step / evidence / confidence) are filled when the prompt
    version is structured (v3) or parseable (v2).

    `seed` makes the call deterministic for the same input (useful for agreement testing
    across runs at higher temperature). `temperature` controls sampling variance.

    raises BudgetExceeded when today's spend meets the daily limit.
    raises CircuitOpen when the breaker is currently open.
    retries rate limits / 5xx within a single call; the breaker tracks call-level outcome."""
    budget.check()
    breaker.before_call()
    _publish_state()

    v = version or PROMPT_VERSION
    system, user_template = get_prompt(v)
    user_msg = user_template.format(window=window_seconds, log_text=log_text)

    request_kwargs: dict = {
        "model": AZURE_OPENAI_DEPLOYMENT,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": temperature,
        "max_tokens": 400,
    }
    if seed is not None:
        request_kwargs["seed"] = seed
    if v in STRUCTURED_VERSIONS:
        request_kwargs["response_format"] = {"type": "json_object"}

    last_err: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            resp = client().chat.completions.create(**request_kwargs)
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
            content = (resp.choices[0].message.content or "").strip()
            breaker.on_success()
            _publish_state()
            return _enrich(AnalysisResult(raw_text=content, model=AZURE_OPENAI_DEPLOYMENT, prompt_version=v))
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
