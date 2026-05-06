"""v2 — adds two pressure points over v1:
1. demand the candidate signal (db / auth / network / memory / config / upstream / cache / kafka / other)
   so downstream code can route by class, and so an evaluator scoring keywords gets a stable handle.
2. force a confidence band. discourages the model from confidently labeling sparse logs.

run via PROMPT_VERSION=v2."""

SYSTEM = (
    "you are a backend log triage assistant for production services. you receive a correlated "
    "bundle of logs from a single trace_id within a small time window and must label the root cause. "
    "be terse. quote evidence by timestamp. if the logs are insufficient, say so explicitly rather "
    "than guessing."
)

USER_TEMPLATE = (
    "trace bundle (window={window}s):\n\n"
    "```\n{log_text}\n```\n\n"
    "respond in this exact format:\n"
    "category: <db|auth|network|memory|config|upstream|cache|kafka|other>\n"
    "root_cause: <one sentence, name the specific failing component>\n"
    "next_step: <one concrete action, not 'investigate'>\n"
    "evidence: <list of log timestamps you relied on>\n"
    "confidence: <high|medium|low>"
)
