import logging
import time

from backend import db, llm, metrics
from backend.correlator import correlate, format_window

log = logging.getLogger(__name__)


def process(logs: list[dict], window_seconds: int) -> list[dict]:
    """correlate → llm → persist. returns one result per trace bundle."""
    bundles = correlate(logs, window_seconds=window_seconds)
    metrics.windows_correlated.inc(len(bundles))

    results: list[dict] = []
    for trace_id, bundle in bundles.items():
        text = format_window(bundle)
        try:
            t0 = time.perf_counter()
            analysis, model = llm.analyze(text, window_seconds)
            metrics.llm_latency.observe(time.perf_counter() - t0)
            metrics.llm_calls.labels(status="ok").inc()
        except Exception:
            metrics.llm_calls.labels(status="error").inc()
            log.exception("llm analyze failed trace_id=%s", trace_id)
            continue

        try:
            db.save_analysis(trace_id, text, analysis, model)
            metrics.analyses_persisted.inc()
        except Exception:
            log.exception("db save failed trace_id=%s", trace_id)

        results.append(
            {
                "trace_id": trace_id,
                "log_text": text,
                "analysis": analysis,
                "model": model,
            }
        )
    return results
