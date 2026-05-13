# Conductor Roadmap (post-MVP)

The MVP Conductor (shipped Phase 1) covers agent registration, capability-
based discovery, single-hop delegation, linear pipelines, sync pub/sub
event bus, and Trajectory-integrated AGENT_HANDOFF recording. The AgentCard
shape is the precursor to A2A v1.0 — field names chosen to map 1:1 to A2A.
The following are deferred to Phase 2+.

## Phase 2 (M2 — hardening)
- [ ] Async EventBus + async delegation paths
- [ ] Retry policies on delegation (with jitter, exponential backoff)
- [ ] Branching pipelines (if/else by step output)
- [ ] Parallel pipeline steps (fan-out / fan-in)
- [ ] Pipeline persistence: save/resume pipeline state via Storage Protocol
- [ ] Conversation graph: multi-turn agent dialogues (not just single delegation)
- [ ] OTel spans on every delegation
- [ ] Per-agent rate limiting (Guardian integration)

## Phase 2.5 (A2A Protocol Compliance — dedicated phase)
- [ ] A2A v1.0 wire format serializer (AgentCard → A2A AgentCard)
- [ ] A2A v1.0 deserializer (A2A AgentCard → PRIMAL AgentCard)
- [ ] HTTP server: expose Conductor.list_agents over A2A discovery endpoint
- [ ] HTTP client: discover remote A2A agents and register them locally
- [ ] MCP↔A2A bridge: register MCP servers as A2A agents (tool-as-agent pattern)
- [ ] Authentication / signing for cross-org A2A calls
- [ ] AAIF registry listing

## Phase 3+ (productization)
- [ ] Smart agent selection (delegated to Atlas — capability + bandit + cost)
- [ ] Conversation graph visualization (Inspector UI)
- [ ] Cost-aware routing across agents (not just models)
- [ ] Multi-tenancy: per-tenant agent registries
- [ ] Agent reputation scores (from Verifier verdicts across N delegations)
- [ ] Negotiation protocol (agents propose/counter-propose delegation terms)

## Non-goals
- We don't run agents in a sandbox here — that's Verifier.sandbox / Harness territory
- We don't define WHICH model an agent uses — that's Atlas territory
- We don't decide WHETHER to delegate at all — that's the user's call (or Guardian's)
- We don't implement A2A wire format in MVP — Phase 2.5 owns that work
