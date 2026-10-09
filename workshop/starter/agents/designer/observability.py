"""Langfuse observability for the AI Creative Studio agents.

One call, `setup_observability("<agent-name>")`, makes an agent fully traceable
in Langfuse:

  * Agent runs, every LLM call and every tool call (FunctionTool, AgentTool,
    SkillToolset, google_search, ...) become spans via the OpenInference ADK
    instrumentor.
  * Outgoing A2A calls (httpx) and incoming A2A requests (Starlette) are
    instrumented and carry the W3C `traceparent` header, so a campaign that
    flows Creative Director -> specialists shows up as ONE trace.

Tracing is strictly opt-in: if LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are not
set, everything here is a no-op and the agents behave exactly as before.

Environment variables (all read by the Langfuse SDK except the last two):
    LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
    LANGFUSE_BASE_URL            e.g. https://cloud.langfuse.com (EU, default)
                                 or https://us.cloud.langfuse.com (US)
    LANGFUSE_TRACING_ENVIRONMENT e.g. local / production
    LANGFUSE_ENABLED             set to "false" to switch tracing off
"""

import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger("ai_creative_studio.observability")

_initialized = False
_tracer_provider = None  # Langfuse's private provider (see setup_observability)
_instrumented_apps: set[int] = set()

# Server-side scopes exported on top of Langfuse's defaults (gen_ai /
# OpenInference / Langfuse spans). Together with the outgoing httpx spans they
# give the trace its cross-agent skeleton:
#   tool call -> HTTP request -> remote agent server -> remote agent run
_SERVER_SCOPES = (
    "opentelemetry.instrumentation.starlette",
    "opentelemetry.instrumentation.asgi",
)


_SKIP_ATTR = "ai_creative_studio.skip_export"
_GENAI_SCOPE = "openinference.instrumentation.google_genai"
_ADK_SCOPE = "openinference.instrumentation.google_adk"


class _DropNestedGenaiSpans:
    """Marks google-genai spans that sit directly under an ADK LLM span.

    ADK already records each of its model calls (`call_llm`, with usage). The
    google-genai instrumentor would add a second LLM span beneath it for the
    same request and Langfuse would count the tokens twice. Only genai calls
    made from inside a tool (parent is not an ADK LLM span) are kept.
    """

    def on_start(self, span, parent_context=None):
        from opentelemetry import trace

        scope = getattr(span.instrumentation_scope, "name", "") or ""
        if not scope.startswith(_GENAI_SCOPE):
            return
        parent = trace.get_current_span(parent_context)
        parent_scope = getattr(getattr(parent, "instrumentation_scope", None), "name", "") or ""
        if parent_scope.startswith(_ADK_SCOPE):
            span.set_attribute(_SKIP_ATTR, True)

    def on_end(self, span):
        pass

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


def langfuse_enabled() -> bool:
    """True when Langfuse credentials are configured and tracing isn't disabled."""
    if os.getenv("LANGFUSE_ENABLED", "true").strip().lower() in ("0", "false", "no"):
        return False
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def _a2a_hosts() -> set[str]:
    """Hosts of the configured specialist agents (the *_AGENT_URL env vars)."""
    hosts = set()
    for key, value in os.environ.items():
        if key.endswith("_AGENT_URL") and value:
            netloc = urlparse(value).netloc
            if netloc:
                hosts.add(netloc)
    return hosts


def _should_export_span(span) -> bool:
    """Langfuse's default span filter plus the A2A HTTP spans.

    Outgoing httpx spans are exported only for calls to the specialist agents:
    every other HTTP call (Gemini, GCS, Langfuse's own uploads) would just be
    noise, and exporting Langfuse's own requests would feed back on itself.
    """
    from langfuse.span_filter import is_default_export_span

    attrs = span.attributes or {}
    if attrs.get(_SKIP_ATTR):
        return False
    if is_default_export_span(span):
        return True
    scope = getattr(span.instrumentation_scope, "name", "") or ""
    if scope.startswith("opentelemetry.instrumentation.httpx"):
        url = attrs.get("http.url") or attrs.get("url.full") or ""
        return urlparse(str(url)).netloc in _a2a_hosts()
    if scope.startswith(_SERVER_SCOPES):
        # Request-level server spans only; drop ASGI receive/send sub-spans.
        return not attrs.get("asgi.event.type")
    return False


def setup_observability(service_name: str) -> bool:
    """Initialise Langfuse tracing for this process. Safe to call repeatedly.

    Args:
        service_name: Logical agent name (e.g. "copywriter"). Recorded as the
            OpenTelemetry `service.name` resource attribute on every span.

    Returns:
        True if tracing is active, False if it is disabled / not configured.
    """
    global _initialized
    if _initialized:
        return True
    if not langfuse_enabled():
        logger.info(
            "Langfuse tracing disabled (LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY not set)"
        )
        return False

    global _tracer_provider
    try:
        from langfuse import Langfuse
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        # Langfuse gets its OWN TracerProvider instead of the process-global one.
        # On Vertex AI Agent Engine the runtime replaces/shuts down the span
        # processors of the global provider during set-up, which would silently
        # kill the Langfuse exporter. A private provider is immune to that and
        # does not interfere with Cloud Trace. Trace context is still shared
        # (contextvars + W3C headers), so parent/child links are preserved.
        resource_attrs = {"service.name": service_name}
        environment = os.getenv("LANGFUSE_TRACING_ENVIRONMENT")
        if environment:
            resource_attrs["langfuse.environment"] = environment
        release = os.getenv("LANGFUSE_RELEASE")
        if release:
            resource_attrs["langfuse.release"] = release
        _tracer_provider = TracerProvider(resource=Resource.create(resource_attrs))
        # Must be registered before Langfuse's own span processor.
        _tracer_provider.add_span_processor(_DropNestedGenaiSpans())

        Langfuse(
            tracer_provider=_tracer_provider,
            should_export_span=_should_export_span,
            environment=environment or None,
        )

        # Agent, LLM and tool-call spans.
        GoogleADKInstrumentor().instrument(tracer_provider=_tracer_provider)
        # Direct google-genai calls made inside tools (e.g. image generation and
        # review). Model name, prompt text and token usage are kept; response
        # bodies and input images are hidden so generated images (large base64
        # payloads) are never uploaded to Langfuse.
        from openinference.instrumentation import TraceConfig
        from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

        GoogleGenAIInstrumentor().instrument(
            tracer_provider=_tracer_provider,
            config=TraceConfig(hide_outputs=True, hide_input_images=True),
        )
        # Propagate trace context over A2A (agent -> agent HTTP calls).
        HTTPXClientInstrumentor().instrument(tracer_provider=_tracer_provider)

        _initialized = True
        logger.info("Langfuse tracing enabled for %s", service_name)
        return True
    except Exception:  # never let observability break the agent
        logger.exception("Failed to initialise Langfuse tracing; continuing without it")
        return False


def instrument_a2a_app(app):
    """Trace incoming A2A requests on a Starlette app returned by `to_a2a`.

    Extracts the caller's `traceparent` so this agent's spans join the
    Creative Director's trace. No-op when tracing is not active.
    """
    if not _initialized or id(app) in _instrumented_apps:
        return app
    try:
        from opentelemetry.instrumentation.starlette import StarletteInstrumentor

        StarletteInstrumentor.instrument_app(app, tracer_provider=_tracer_provider)
        _instrumented_apps.add(id(app))
    except Exception:
        logger.exception("Failed to instrument the A2A server app for tracing")
    return app


def flush_observability() -> None:
    """Send any buffered spans to Langfuse (call before a short-lived process exits)."""
    if not _initialized:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:
        logger.exception("Failed to flush Langfuse")
