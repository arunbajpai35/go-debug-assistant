"""opentelemetry setup. exports spans to OTLP if OTEL_EXPORTER_OTLP_ENDPOINT is set,
otherwise falls back to console for local dev. fastapi + psycopg2 are auto-instrumented."""
import logging
import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

log = logging.getLogger(__name__)

_initialized = False


def init(service_name: str = "debug-assistant") -> None:
    global _initialized
    if _initialized:
        return
    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        log.info("otel: exporting to %s", os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"])
    elif os.getenv("OTEL_CONSOLE", "").lower() in ("1", "true", "yes"):
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        log.info("otel: exporting to console")
    else:
        log.info("otel: configured (no exporter set; spans recorded but not emitted)")
    trace.set_tracer_provider(provider)
    Psycopg2Instrumentor().instrument()
    _initialized = True


def instrument_fastapi(app) -> None:
    FastAPIInstrumentor.instrument_app(app)


tracer = trace.get_tracer("debug-assistant")
