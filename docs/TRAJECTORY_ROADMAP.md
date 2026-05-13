# Trajectory Roadmap (post-MVP)

The MVP Trajectory (shipped Phase 1) covers context-manager recording, the
nine canonical step kinds, full JSON serialization, replay/filter helpers,
Storage Protocol persistence, and Guardian-violation handoff. The following
are commercial differentiators deferred to Phase 2+ hardening.

## Phase 2 (M2 — hardening)
- [ ] OpenTelemetry span emission (every step → OTel span)
- [ ] OTLP exporter for shipping trajectories to PRIMAL Cloud
- [ ] Sampling: head-based, tail-based, error-biased
- [ ] Streaming trajectories (yield steps as they happen, not just on completion)
- [ ] Trajectory diffing: compare two runs of the same agent on the same input
- [ ] Causal-graph rendering helpers (for the Inspector UI)
- [ ] Time-travel debugger surface (step backward/forward in a saved trajectory)
- [ ] Cross-agent trajectory propagation via Conductor (W3C trace-context style).
- [ ] Cost/latency rollups across ROUTING_DECISION steps (Atlas integration).

## Phase 3+ (productization)
- [ ] Distributed trajectories across A2A agent boundaries (W3C trace-context propagation)
- [ ] Trajectory bundles (parent + N children as one shippable artifact)
- [ ] Encryption-at-rest for sensitive payloads (configurable redaction at store time)
- [ ] Query DSL: "find all trajectories where tool=stripe AND cost>$0.50 AND status=FAILED"
- [ ] Index/search backend integration (Postgres GIN, Meilisearch, etc.)
- [ ] Cost rollups: per-agent, per-tool, per-customer
- [ ] Replay-against-new-policies: feed an old trajectory through a new Guardian config

## Non-goals
- We don't store agent SOURCE CODE alongside trajectories (separate concern)
- We don't run the agent during replay (replay is read-only by design — Verifier territory)
- We don't ship a UI (that's primal-inspector's job)
