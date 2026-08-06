#!/usr/bin/env python3
"""Tests for agentloop.telemetry.

The core contract: with no endpoint/keys configured, both exporters are
zero-overhead no-ops (AgentLoop's default install has zero runtime deps).
With telemetry configured but the optional package missing, they degrade
gracefully instead of crashing.
"""
import os

# Ensure unconfigured state BEFORE importing the module
os.environ.pop("AGENTLOOP_OTEL_ENDPOINT", None)
os.environ.pop("HONEYCOMB_API_KEY", None)
os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
os.environ.pop("LANGFUSE_SECRET_KEY", None)

from agentloop.telemetry import LangfuseExporter, TelemetryExporter, is_any_telemetry_enabled

# 1. Unconfigured -> disabled; every method is a safe no-op
t = TelemetryExporter()
assert t.enabled is False, "unconfigured TelemetryExporter must be disabled"
t.start_span("iter.1", {"iter": "1", "goal_hash": "abc"})
t.record_event("iteration.end", {"outcome": "retry"})
t.finish_span()
t.finish_span()  # idempotent
print("TELEMETRY NO-OP (unconfigured): PASS")

lf = LangfuseExporter()
assert lf.enabled is False, "unconfigured LangfuseExporter must be disabled"
lf.start_trace("iter.1")
lf.record_generation(name="g", model="m", usage={"input": 1, "output": 1})
lf.finish()
print("LANGFUSE NO-OP (unconfigured): PASS")

assert is_any_telemetry_enabled() is False
print("TELEMETRY DETECTION (off): PASS")

# 2. Configured endpoint but optional dep not installed -> graceful no-op
os.environ["AGENTLOOP_OTEL_ENDPOINT"] = "http://localhost:4318/v1/traces"
t2 = TelemetryExporter()
t2.start_span("s", {"k": "v"})   # must not raise
t2.record_event("e")
t2.finish_span()
os.environ.pop("AGENTLOOP_OTEL_ENDPOINT", None)
print("TELEMETRY MISSING-DEP DEGRADE (no crash): PASS")

os.environ["LANGFUSE_PUBLIC_KEY"] = "pk-lf-test"
os.environ["LANGFUSE_SECRET_KEY"] = "sk-lf-test"
lf2 = LangfuseExporter()
lf2.start_trace("t")             # must not raise
lf2.record_generation(name="g")
lf2.finish()
os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
os.environ.pop("LANGFUSE_SECRET_KEY", None)
print("LANGFUSE MISSING-DEP DEGRADE (no crash): PASS")

print("\nALL TELEMETRY TESTS PASSED")
