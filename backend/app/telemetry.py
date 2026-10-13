"""Optional, content-safe OpenTelemetry helpers."""

from contextlib import nullcontext
from typing import Any

from app.config import Settings

try:
    from opentelemetry import metrics, propagate, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    OTEL_AVAILABLE = True
except ImportError:  # Optional until the deployment installs the observability extras.
    OTEL_AVAILABLE = False


def configure_telemetry(settings: Settings, app: Any = None, engine: Any = None, service_name: str | None = None) -> None:
    if not settings.otel_enabled or not OTEL_AVAILABLE:
        return
    resource = Resource.create({"service.name": service_name or settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/") if settings.otel_exporter_otlp_endpoint else None
    trace_endpoint = f"{endpoint}/v1/traces" if endpoint and not endpoint.endswith("/v1/traces") else endpoint
    metric_endpoint = f"{endpoint}/v1/metrics" if endpoint and not endpoint.endswith("/v1/metrics") else endpoint
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=trace_endpoint)))
    trace.set_tracer_provider(provider)
    reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=metric_endpoint))
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
    if engine is not None:
        SQLAlchemyInstrumentor().instrument(engine=engine)
    RedisInstrumentor().instrument()


def current_trace_id() -> str | None:
    if not OTEL_AVAILABLE:
        return None
    context = trace.get_current_span().get_span_context()
    return format(context.trace_id, "032x") if context.is_valid else None


def inject_trace_context() -> dict[str, str]:
    if not OTEL_AVAILABLE:
        return {}
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier


def extract_trace_context(carrier: dict[str, str] | None) -> Any:
    if not OTEL_AVAILABLE:
        return None
    return propagate.extract(carrier or {})


def span(name: str, attributes: dict[str, str | int | float | bool] | None = None, context: Any = None):
    if not OTEL_AVAILABLE:
        return nullcontext()
    tracer = trace.get_tracer("answerforge")
    return tracer.start_as_current_span(name, context=context, attributes=attributes or {})
