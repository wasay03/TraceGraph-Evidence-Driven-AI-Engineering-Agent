import logging
import re

from opentelemetry import trace

logger = logging.getLogger(__name__)
_FUNCTION = re.compile(r"\b(tg_\w+)\s*\(")
_configured = False


def tracer() -> trace.Tracer:
    """
    #Feature: Tracing (PRD observability)
    #Scenario: Spans nest run -> phase -> tool call -> engine operator -> SQL function; no-ops until configured
    #Complexity: Time O(1) - constant
    """
    return trace.get_tracer("tracegraph")


def sql_function(statement: str) -> str:
    """
    #Feature: Tracing
    #Scenario: Stored function a statement calls, as the SQL span name
    #Complexity: Time O(s) - statement length
    """
    match = _FUNCTION.search(statement)
    return match.group(1) if match else "sql"


def configure_tracing(exporter: str) -> None:
    """
    #Feature: Tracing
    #Scenario: TG_OTEL_EXPORTER=console prints spans, otlp sends them to OTEL_EXPORTER_OTLP_ENDPOINT; empty keeps
               the no-op tracer. Needs the otel extra; without it a warning is logged and tracing stays off.
    #Complexity: Time O(1) - constant
    """
    global _configured
    if not exporter or _configured:
        return
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError:
        logger.warning("Tracing requested but opentelemetry-sdk is not installed; pip install -e '.[otel]'.")
        return
    if exporter == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        except ImportError:
            logger.warning("TG_OTEL_EXPORTER=otlp needs opentelemetry-exporter-otlp-proto-http.")
            return
        span_exporter = OTLPSpanExporter()
    else:
        span_exporter = ConsoleSpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "tracegraph"}))
    provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    _configured = True
