import logging
import time

from openai import APIError, AzureOpenAI, RateLimitError

from backend.config import (
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_KEY,
    LLM_MAX_RETRIES,
    LLM_TIMEOUT_SECONDS,
)

log = logging.getLogger(__name__)


SYSTEM_PROMPT = (
    "you are a backend log triage assistant. given a correlated bundle of logs from a single trace, "
    "produce a concise root-cause hypothesis and one suggested next step. "
    "be specific. cite log lines by timestamp when relevant. avoid hedging."
)

USER_TEMPLATE = (
    "logs (correlated by trace_id within a {window}s window):\n\n"
    "```\n{log_text}\n```\n\n"
    "respond in this format:\n"
    "root_cause: <one sentence>\n"
    "next_step: <one sentence>\n"
    "evidence: <log timestamps you used>"
)


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


def analyze(log_text: str, window_seconds: int) -> tuple[str, str]:
    """returns (analysis_text, model_name). retries on rate limits with exponential backoff."""
    user_msg = USER_TEMPLATE.format(window=window_seconds, log_text=log_text)
    last_err: Exception | None = None
    for attempt in range(LLM_MAX_RETRIES + 1):
        try:
            resp = client().chat.completions.create(
                model=AZURE_OPENAI_DEPLOYMENT,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=400,
            )
            return resp.choices[0].message.content.strip(), AZURE_OPENAI_DEPLOYMENT
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
    raise RuntimeError(f"llm call failed after {LLM_MAX_RETRIES + 1} attempts: {last_err}")
