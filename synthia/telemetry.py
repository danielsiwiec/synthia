import logging
import os
import uuid
from collections.abc import Awaitable, Callable
from contextlib import AbstractContextManager
from functools import wraps
from typing import Any, TypeVar

from langsmith.integrations.claude_agent_sdk import configure_claude_agent_sdk
from opentelemetry import _logs, metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

_SERVICE_NAME = "synthia"
_SERVICE_INSTANCE_ID = str(uuid.uuid4())[:8]
_OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
_OTEL_ENABLED = bool(_OTEL_ENDPOINT)
_LANGSMITH_ENABLED = bool(os.getenv("LANGSMITH_API_KEY"))

_tracer: trace.Tracer | None = None
_otel_logger: logging.Logger | None = None
_logger_provider: LoggerProvider | None = None
_log_handler: LoggingHandler | None = None


def setup_telemetry() -> None:
    global _tracer, _otel_logger, _logger_provider, _log_handler

    if _LANGSMITH_ENABLED:
        configure_claude_agent_sdk()

    resource = Resource.create(
        {
            "service.name": _SERVICE_NAME,
            "service.version": "0.1.0",
            "service.instance.id": _SERVICE_INSTANCE_ID,
        }
    )

    trace_provider = TracerProvider(resource=resource)
    if _OTEL_ENABLED:
        trace_exporter = OTLPSpanExporter(endpoint=_OTEL_ENDPOINT, insecure=True)
        trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(_SERVICE_NAME)

    if _OTEL_ENABLED:
        metric_reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=_OTEL_ENDPOINT, insecure=True),
            export_interval_millis=15000,
        )
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    _logger_provider = LoggerProvider(resource=resource)
    if _OTEL_ENABLED:
        log_exporter = OTLPLogExporter(endpoint=_OTEL_ENDPOINT, insecure=True)
        _logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    _logs.set_logger_provider(_logger_provider)

    _log_handler = LoggingHandler(level=logging.DEBUG, logger_provider=_logger_provider)
    _otel_logger = logging.getLogger("synthia.otel")
    _otel_logger.setLevel(logging.DEBUG)
    _otel_logger.addHandler(_log_handler)
    _otel_logger.propagate = False


def loguru_otel_sink(message: Any) -> None:
    otel_logger = _otel_logger or logging.getLogger("synthia.otel")
    otel_logger.disabled = False
    record = message.record
    level_map = {
        "TRACE": logging.DEBUG,
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "SUCCESS": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    otel_logger.log(level_map.get(record["level"].name, logging.INFO), record["message"], extra=record["extra"])


def instrument_fastapi(app: Any) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def current_span() -> trace.Span:
    return trace.get_current_span()


def start_span(name: str) -> AbstractContextManager[trace.Span]:
    tracer = _tracer or trace.get_tracer(_SERVICE_NAME)
    return tracer.start_as_current_span(name)


def traced(name: str | None = None) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        span_name = name or getattr(func, "__name__", "unknown")

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = _tracer or trace.get_tracer(_SERVICE_NAME)
            with tracer.start_as_current_span(span_name) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper  # type: ignore[return-value]  # ty: ignore[invalid-return-type]

    return decorator
