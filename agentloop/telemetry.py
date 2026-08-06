"""
telemetry.py — optional observability exporters for AgentLoop.

Two exporters, both zero-overhead when unconfigured:

  * TelemetryExporter — one OpenTelemetry span per loop iteration, exported
    over OTLP (Honeycomb, Jaeger, Tempo, Datadog…). Enabled when
    AGENTLOOP_OTEL_ENDPOINT is set. The opentelemetry-* packages are optional
    (pip install 'agentloop[otlp]').

  * LangfuseExporter — one Langfuse trace per iteration with a generation
    child. Enabled when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.
    The `langfuse` package is optional (pip install 'agentloop[langfuse]').

If the optional dependency is missing the exporter silently disables itself
— AgentLoop must keep its zero-runtime-dependency default install.
"""
import os
from typing import Any


class TelemetryExporter:
    """OpenTelemetry iteration spans. No-op unless AGENTLOOP_OTEL_ENDPOINT is set."""

    def __init__(self) -> None:
        self._enabled = bool(os.environ.get("AGENTLOOP_OTEL_ENDPOINT"))
        self._tracer: Any = None
        self._current_span: Any = None
        if self._enabled:
            try:
                # Dynamic imports: opentelemetry-* is an optional dependency
                # (extras: otlp). Static imports would fail without it.
                import importlib

                trace = importlib.import_module("opentelemetry.trace")
                _exp = importlib.import_module(
                    "opentelemetry.exporter.otlp.proto.http.trace_exporter")
                otlp_exporter = _exp.OTLPSpanExporter
                sdk_resources = importlib.import_module("opentelemetry.sdk.resources")
                sdk_trace = importlib.import_module("opentelemetry.sdk.trace")
                sdk_trace_export = importlib.import_module("opentelemetry.sdk.trace.export")

                endpoint = os.environ["AGENTLOOP_OTEL_ENDPOINT"]
                headers: dict[str, str] = {}
                honeycomb_key = os.environ.get("HONEYCOMB_API_KEY", "")
                if honeycomb_key:
                    headers["x-honeycomb-team"] = honeycomb_key
                provider = sdk_trace.TracerProvider(
                    resource=sdk_resources.Resource.create({"service.name": "agentloop"}))
                provider.add_span_processor(
                    sdk_trace_export.BatchSpanProcessor(
                        otlp_exporter(endpoint=endpoint, headers=headers)))
                trace.set_tracer_provider(provider)
                self._tracer = trace.get_tracer("agentloop")
            except Exception:
                # Optional dep missing or bad endpoint config — degrade to no-op.
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start_span(self, name: str, attrs: dict[str, Any] | None = None) -> None:
        if not self._enabled or self._tracer is None:
            return
        span = self._tracer.start_span(name)
        for key, val in (attrs or {}).items():
            span.set_attribute(key, str(val))
        self._current_span = span

    def record_event(self, name: str, attrs: dict[str, Any] | None = None) -> None:
        if not self._enabled or self._current_span is None:
            return
        self._current_span.add_event(
            name, attributes={k: str(v) for k, v in (attrs or {}).items()}
        )

    def finish_span(self) -> None:
        if self._enabled and self._current_span is not None:
            try:
                self._current_span.end()
            except Exception:
                pass
            self._current_span = None


class LangfuseExporter:
    """Langfuse trace per iteration. Enabled when Langfuse keys are set."""

    def __init__(self) -> None:
        self._enabled = bool(
            os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
        )
        self._client: Any = None
        self._trace: Any = None
        if self._enabled:
            try:
                import importlib

                _langfuse_mod = importlib.import_module("langfuse")
                langfuse_cls = _langfuse_mod.Langfuse
                self._client = langfuse_cls(
                    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                    host=os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )
            except Exception:
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start_trace(self, name: str, attrs: dict[str, Any] | None = None) -> None:
        if not self._enabled or self._client is None:
            return
        try:
            self._trace = self._client.trace(name=name, input=attrs or {})
        except Exception:
            self._trace = None

    def record_generation(self, **kwargs: Any) -> None:
        if not self._enabled or self._client is None or self._trace is None:
            return
        try:
            self._trace.generation(**kwargs)
        except Exception:
            pass

    def finish(self) -> None:
        if not self._enabled or self._client is None:
            return
        try:
            self._client.flush()
        except Exception:
            pass


def is_any_telemetry_enabled() -> bool:
    """True if any telemetry backend is configured and usable."""
    return bool(os.environ.get("AGENTLOOP_OTEL_ENDPOINT")) or bool(
        os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")
    )
