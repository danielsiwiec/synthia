import logging
import os
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

_SERVICE_NAME = "synthia"
_OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

_tracer: trace.Tracer | None = None
_otel_logger: logging.Logger | None = None


def setup_telemetry() -> None:
    global _tracer, _otel_logger

    resource = Resource.create({"service.name": _SERVICE_NAME, "service.version": "0.1.0"})

    trace_provider = TracerProvider(resource=resource)
    trace_exporter = OTLPSpanExporter(endpoint=_OTEL_ENDPOINT, insecure=True)
    trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(_SERVICE_NAME)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=_OTEL_ENDPOINT, insecure=True),
        export_interval_millis=15000,
    )
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[metric_reader]))

    logger_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint=_OTEL_ENDPOINT, insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    handler = LoggingHandler(level=logging.DEBUG, logger_provider=logger_provider)
    _otel_logger = logging.getLogger("synthia.otel")
    _otel_logger.setLevel(logging.DEBUG)
    _otel_logger.addHandler(handler)


def loguru_otel_sink(message: Any) -> None:
    otel_logger = _otel_logger or logging.getLogger("synthia.otel")
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
    otel_logger.log(level_map.get(record["level"].name, logging.INFO), record["message"])


def instrument_fastapi(app: Any) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")


F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def current_span() -> trace.Span:
    return trace.get_current_span()


def start_span(name: str) -> trace.Span:
    tracer = _tracer or trace.get_tracer(_SERVICE_NAME)
    return tracer.start_span(name)


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

        return wrapper  # type: ignore[return-value]

    return decorator
