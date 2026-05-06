import json
import logging
import time

from backend import db, llm, metrics
from backend.correlator import correlate, format_window
from backend.tracing import tracer

log = logging.getLogger(__name__)


def process(logs: list[dict], window_seconds: int) -> list[dict]:
    """correlate → llm → persist. returns one result per trace bundle.

    persistence is batched into a single insert at the end so wide bundle
    counts don't pay N round-trips to postgres.
    """
    with tracer.start_as_current_span("pipeline.process") as root:
        root.set_attribute("logs.count", len(logs))
        root.set_attribute("window.seconds", window_seconds)

        try:
            with tracer.start_as_current_span("db.save_raw_logs_batch") as span:
                db.save_raw_logs_batch(logs)
                span.set_attribute("rows", len(logs))
                metrics.raw_logs_persisted.inc(len(logs))
        except Exception:
            log.exception("raw_logs save failed; continuing with correlation")

        with tracer.start_as_current_span("correlate"):
            bundles = correlate(logs, window_seconds=window_seconds)
        metrics.windows_correlated.inc(len(bundles))
        root.set_attribute("bundles.count", len(bundles))

        results: list[dict] = []
        rows: list[db.AnalysisRow] = []
        for trace_id, bundle in bundles.items():
            with tracer.start_as_current_span("process_bundle") as span:
                span.set_attribute("trace_id", trace_id)
                span.set_attribute("bundle.size", len(bundle))
                text = format_window(bundle)
                try:
                    with tracer.start_as_current_span("llm.analyze") as llm_span:
                        t0 = time.perf_counter()
                        result = llm.analyze(text, window_seconds)
                        metrics.llm_latency.observe(time.perf_counter() - t0)
                        metrics.llm_calls.labels(status="ok").inc()
                        llm_span.set_attribute("prompt.version", result.prompt_version)
                        if result.category:
                            llm_span.set_attribute("analysis.category", result.category)
                        if result.confidence:
                            llm_span.set_attribute("analysis.confidence", result.confidence)
                except Exception:
                    metrics.llm_calls.labels(status="error").inc()
                    span.set_attribute("error", True)
                    log.exception("llm analyze failed trace_id=%s", trace_id)
                    continue

                evidence_json = json.dumps(result.evidence) if result.evidence else None
                rows.append(
                    (
                        trace_id,
                        text,
                        result.raw_text,
                        result.model,
                        result.prompt_version,
                        result.category,
                        result.root_cause,
                        result.next_step,
                        evidence_json,
                        result.confidence,
                    )
                )
                results.append(
                    {
                        "trace_id": trace_id,
                        "log_text": text,
                        "analysis": result.raw_text,
                        "model": result.model,
                        "prompt_version": result.prompt_version,
                        "category": result.category,
                        "root_cause": result.root_cause,
                        "next_step": result.next_step,
                        "evidence": result.evidence,
                        "confidence": result.confidence,
                    }
                )

        if rows:
            try:
                with tracer.start_as_current_span("db.save_analyses_batch") as span:
                    span.set_attribute("rows", len(rows))
                    db.save_analyses_batch(rows)
                    metrics.analyses_persisted.inc(len(rows))
            except Exception:
                log.exception("batch save failed rows=%d", len(rows))

        return results
