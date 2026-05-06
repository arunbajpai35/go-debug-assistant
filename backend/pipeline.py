import logging
import time

from backend import db, llm, metrics
from backend.correlator import correlate, format_window
from backend.tracing import tracer

log = logging.getLogger(__name__)


def process(logs: list[dict], window_seconds: int) -> list[dict]:
    """correlate → llm → persist. returns one result per trace bundle."""
    with tracer.start_as_current_span("pipeline.process") as root:
        root.set_attribute("logs.count", len(logs))
        root.set_attribute("window.seconds", window_seconds)

        with tracer.start_as_current_span("correlate"):
            bundles = correlate(logs, window_seconds=window_seconds)
        metrics.windows_correlated.inc(len(bundles))
        root.set_attribute("bundles.count", len(bundles))

        results: list[dict] = []
        for trace_id, bundle in bundles.items():
            with tracer.start_as_current_span("process_bundle") as span:
                span.set_attribute("trace_id", trace_id)
                span.set_attribute("bundle.size", len(bundle))
                text = format_window(bundle)
                try:
                    with tracer.start_as_current_span("llm.analyze"):
                        t0 = time.perf_counter()
                        analysis, model = llm.analyze(text, window_seconds)
                        metrics.llm_latency.observe(time.perf_counter() - t0)
                        metrics.llm_calls.labels(status="ok").inc()
                except Exception:
                    metrics.llm_calls.labels(status="error").inc()
                    span.set_attribute("error", True)
                    log.exception("llm analyze failed trace_id=%s", trace_id)
                    continue

                try:
                    with tracer.start_as_current_span("db.save_analysis"):
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
