# Observability — OpenTelemetry Spans

PRIMAL emits OpenTelemetry spans across every observable pillar. Install
the optional `[otel]` extra and configure any OTel-compatible host
(Datadog, Honeycomb, Grafana Tempo, New Relic, …) — PRIMAL spans appear
in your traces with zero further wiring.

## Install

```bash
pip install primal-ai[otel]
```

This pulls in `opentelemetry-api`. You still need an SDK + exporter
(your vendor will provide one, or use `opentelemetry-sdk` +
`opentelemetry-exporter-otlp` directly).

## Quick example — Honeycomb

> Verified against honeycomb-io and ddtrace docs as of 2026-05-14.

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

resource = Resource.create({"service.name": "my-agent"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(
            endpoint="https://api.honeycomb.io/v1/traces",
            headers={"x-honeycomb-team": "YOUR_API_KEY"},
        ),
    ),
)
trace.set_tracer_provider(provider)

# ... use PRIMAL as usual — spans flow automatically ...
```

## Quick example — Datadog

```python
from ddtrace.opentelemetry import TracerProvider
from opentelemetry import trace

trace.set_tracer_provider(TracerProvider())

# DD_TRACE_OTEL_ENABLED=true ddtrace-run python my_agent.py
```

## Attribute schema — anchored on Trajectory

PRIMAL spans follow one consistent attribute schema, anchored on the
Trajectory pillar:

| Slot | Purpose |
|---|---|
| `primal.<pillar>.id` | Primary identifier (UUID hex) |
| `primal.<pillar>.status` | Terminal state (pillar-specific enum) |
| `primal.<pillar>.duration_ms` | Span duration (float) |
| `primal.<pillar>.<noun>_count` | Counters (`step_count`, `layer_count`, `policy_count`, `candidates_count`, `attempt_count`) |
| `primal.<pillar>.total_cost` / `cost` | Dollar cost (float) |
| `primal.<pillar>.reason` | Human-readable failure description |
| `primal.<pillar>.<sub>.<noun>` | Child-span / sub-op attributes (e.g. `primal.trajectory.step.kind`, `primal.verifier.layer.status`) |
| Span event `primal.<pillar>.<event>` | Point-in-time markers (`primal.trajectory.step`, `primal.guardian.violation`, `primal.atlas.cascade.attempt`) |
| Span event `exception` | OTel-native failure detail (via `record_exception`) |

OTel `Status.ERROR` is set on the span whenever a pillar's `status` is a
failure value — so any trace UI's "errors" filter surfaces PRIMAL
failures without custom configuration.

## Pillar-by-pillar reference

### Trajectory

| Span name | When |
|---|---|
| `primal.trajectory.session` | `with Trajectory.record() as tr:` |
| `primal.trajectory.tool_call` | Paired `record_tool_call` → `record_tool_result` |
| `primal.trajectory.llm_call` | Paired `record_llm_call` → `record_llm_result` |

**Session span attributes:**

```
primal.trajectory.id            (str)    UUID hex
primal.trajectory.agent_id      (str)    "" if none
primal.trajectory.parent_id     (str)    "" if none
primal.trajectory.status        (str)    "SUCCESS" | "FAILED"
primal.trajectory.step_count    (int)
primal.trajectory.duration_ms   (float)
primal.trajectory.total_cost    (float)  0.0 if no cost-bearing steps
primal.trajectory.step_kinds.<kind_lower>  (int)
                                         e.g. .tool_call=3, .output=1
```

**Paired call/result span attributes** (`tool_call` / `llm_call`):

```
primal.trajectory.tool_name | model      (str)
primal.trajectory.cost                   (float | unset)
primal.trajectory.latency_ms             (float | unset)
primal.trajectory.orphaned               (bool, only when no matching result)
primal.trajectory.step.id                (str)  UUID of the originating step
```

**Span events on the session span:**

```
primal.trajectory.step              — fired on unpaired steps
  attrs: primal.trajectory.step.kind, primal.trajectory.step.id

exception                           — via record_exception when FAILED
```

**Unpaired step kinds (become span events, not spans):**
`INPUT`, `OUTPUT`, `ERROR`, `RETRY`, `POLICY_VIOLATION`,
`AGENT_HANDOFF`, `ROUTING_DECISION`. Anything with duration semantics
(call → result pairs) becomes a real span; the rest become events on the
session span. This keeps duration-bearing things as spans and avoids
zero-length clutter.

**Orphan handling:** A `tool_call` / `llm_call` span without a matching
result is closed when the trajectory exits, with
`primal.trajectory.orphaned=True`. If the trajectory exits via an
exception, that exception is also recorded on every open call/result
span — partial tool invocations stay visible in traces.

### Guardian

| Span name | When |
|---|---|
| `primal.guardian.invoke` | Every call to a `Guardian.wrap()`'d agent |

**Attributes:**

```
primal.guardian.policy_count        (int)
primal.guardian.dry_run             (bool)
primal.guardian.status              (str)   "OK" | "VIOLATION" | "AGENT_ERROR"
```

**Span events on the invoke span:**

```
primal.guardian.violation
  attrs: primal.guardian.policy, primal.guardian.reason,
         primal.guardian.phase, primal.guardian.dry_run

exception                           — via record_exception on
                                      VIOLATION or AGENT_ERROR exits
```

`VIOLATION` is distinct from `AGENT_ERROR` so trace filters can separate
"policy fired" from "agent crashed". Dry-run violations still emit the
span event but don't raise.

### Verifier

| Span name | When |
|---|---|
| `primal.verifier.audit` | `Verifier.audit(...)` |
| `primal.verifier.layer` | One per VerifierLayer (child of audit) |

**Audit span attributes:**

```
primal.verifier.layer_count_planned  (int)   layers requested
primal.verifier.target_kind          (str)   "output" | "trajectory"
primal.verifier.status               (str)   "PASS" | "FAIL" | "UNCERTAIN"
primal.verifier.layer_count          (int)   layers actually run
primal.verifier.confidence           (float) mean confidence
primal.verifier.total_cost           (float) sum of layer costs (unset if all None)
```

**Layer span attributes:**

```
primal.verifier.layer.name           (str)
primal.verifier.layer.status         (str)   "PASS" | "FAIL" | "UNCERTAIN"
primal.verifier.layer.confidence     (float)
primal.verifier.layer.latency_ms     (float)
primal.verifier.layer.cost           (float | unset)
```

A layer that raises during `verify(...)` becomes UNCERTAIN with the
exception recorded on its span (OTel `Status.ERROR` + `exception` event).

### Conductor

| Span name | When |
|---|---|
| `primal.conductor.delegate` | `Conductor.delegate(...)` |

**Attributes:**

```
primal.conductor.from_agent          (str)
primal.conductor.to_agent            (str)
primal.conductor.capability          (str)
primal.conductor.task                (str)
primal.conductor.status              (str)   "SUCCESS" | "FAILED" | "TIMEOUT" | "REFUSED"
primal.conductor.duration_ms         (float)
primal.conductor.reason              (str)   set on non-SUCCESS
```

### Atlas

| Span name | When |
|---|---|
| `primal.atlas.route` | `Atlas.route(...)` and the routing phase of `Atlas.invoke(...)` |
| `primal.atlas.provider` | Provider call phase of `Atlas.invoke(...)` (child of route) |
| `primal.atlas.cascade` | `Cascade.run(...)` |
| `primal.atlas.cascade.attempt` | Per provider attempt in a cascade (child of cascade) |

**Route span attributes:**

```
primal.atlas.task                       (str)
primal.atlas.context.capability         (str)
primal.atlas.status                     (str)  "SUCCESS" | "NO_CANDIDATES" | "ALL_UNHEALTHY"
primal.atlas.chosen_provider            (str)  set on SUCCESS
primal.atlas.candidates_count           (int)
primal.atlas.candidates_skipped         (int)
primal.atlas.duration_ms                (float)
primal.atlas.reason                     (str)  set on non-SUCCESS
primal.atlas.selector                   (str)  set when a bandit selector was active
```

**Provider span attributes:**

```
primal.atlas.provider.name              (str)
primal.atlas.provider.status            (str)  "SUCCESS" | "FAILED"
```

**Cascade span attributes:**

```
primal.atlas.cascade.id                 (str)
primal.atlas.cascade.providers          (int)  declared
primal.atlas.cascade.status             (str)  "SUCCESS" | "FAILED" | "ALL_UNHEALTHY"
primal.atlas.cascade.attempt_count      (int)
primal.atlas.cascade.duration_ms        (float)
primal.atlas.cascade.chosen             (str)  set on SUCCESS
```

**Cascade attempt span attributes:**

```
primal.atlas.cascade.id                 (str)
primal.atlas.cascade.attempt.provider   (str)
primal.atlas.cascade.attempt.index      (int)
primal.atlas.cascade.attempt.status     (str)  "SUCCESS" | "FAILED" | "NO_CANDIDATES" | "ALL_UNHEALTHY"
```

## Parent-child relationships

Spans use OTel's native context propagation. Any pillar span opened
inside `with Trajectory.record():` becomes a child of the
`primal.trajectory.session` span. Pillar-to-pillar nesting (e.g.
`Atlas.invoke` inside a `Conductor`-delegated agent) is automatic too —
no manual context plumbing.

A typical trace structure for a Guardian-wrapped agent that talks to a
sub-agent, routes via Atlas, and audits via Verifier looks like:

```
primal.trajectory.session
└── primal.guardian.invoke
    ├── primal.conductor.delegate
    ├── primal.atlas.route
    │   └── primal.atlas.provider
    └── primal.verifier.audit
        ├── primal.verifier.layer
        └── primal.verifier.layer
```

## What's NOT emitted (yet)

- **Metrics** — distinct OTel signal, planned for a future session.
- **Logs** — same.
- **Auto-instrumentation for third-party libraries** (httpx, sqlalchemy,
  …) — out of scope; use the OTel ecosystem's own instrumentation
  packages.
- **Spans for the Storage, Harness, and Continuity pillars** — those
  don't have a clear "operation" boundary today. They may gain spans
  in a later session if usage patterns make them valuable.
