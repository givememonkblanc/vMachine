from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config.settings import get_settings

_tracer: trace.Tracer | None = None


def init_tracer() -> None:
    settings = get_settings()

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "service.version": "0.1.0",
            "deployment.environment": settings.app_env,
        }
    )

    provider = TracerProvider(resource=resource)

    if settings.otel_endpoint:
        otlp_exporter = OTLPSpanExporter(
            endpoint=settings.otel_endpoint,
            insecure=True,
        )
        processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(processor)

    global _tracer
    _tracer = trace.get_tracer(settings.otel_service_name, tracer_provider=provider)
    trace.set_tracer_provider(provider)


def get_tracer(module_name: str = "okastro") -> trace.Tracer:
    if _tracer is None:
        return trace.get_tracer(module_name)
    return _tracer
