# Changelog

All notable changes to PRIMAL (`primal-ai`) are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-05-14

First public release. All seven pillars shipped as MVPs with zero runtime
dependencies. The complete reliability + orchestration + routing + continuity
loop is functional end-to-end.

### Added

- **Guardian** — Runtime policy enforcement. Six built-in policies (RateLimit,
  DollarCap, AllowList, BlockList, SchemaValidator, PIIRedact), sync + async
  wrappers, AllOf/AnyOf composition, string DSL, dry-run mode.
- **Trajectory** — Structured causal recording for every agent execution.
  Eleven step kinds (INPUT, TOOL_CALL, TOOL_RESULT, LLM_CALL, LLM_RESULT,
  ERROR, RETRY, OUTPUT, POLICY_VIOLATION, AGENT_HANDOFF, ROUTING_DECISION),
  context-manager API, replay + filter helpers, Storage Protocol persistence,
  Guardian violation handoff.
- **Verifier** — Three-layer audit (rule-based, BYO LLM judge, domain). Pass/
  fail/uncertain verdicts with confidence and reasons. JSONSchemaVerifier,
  RegexMatchVerifier, RuleBasedVerifier, BYOLLMJudge as the LLM surface.
  Trajectory-aware verification supported.
- **Conductor** — Agent-to-agent orchestration. Capability-based agent
  registry, single-hop delegation, linear pipelines, sync pub/sub EventBus.
  AgentCard shape is an A2A v1.0 precursor (field names map 1:1).
- **Atlas** — Smart routing across providers. Provider Protocol + BYOProvider,
  capability-and-tag discovery, health-aware filtering, exponential-backoff
  cascade with cooldown, deterministic routing by default. Bandit selection
  via Thompson sampling or UCB1 (opt-in), Storage-backed bandit state.
- **Storage** — InMemory and SQLite backends behind a Storage Protocol.
  SQLite uses WAL mode, JSON values, thread-safe per-connection, strict at
  the boundary (non-JSON-serializable values raise TypeError, no silent
  coercion). Postgres + Redis stubs reserved for Phase 2.
- **Harness** — Health monitoring, tool registry (substring + tag, no
  embeddings), interval-based scheduler with single daemon thread. Opt-in
  startup so importing the package never spawns a background thread.
- **Continuity** — Portable UserProfile with source + confidence metadata,
  three merge strategies, BYO autolearn for extracting facts from text via
  user-supplied LLM. Storage-backed persistence.

### Architecture

- Four neutral cross-pillar primitives at the package root: `_jsonschema.py`
  (shared validator), `_trajectory_context.py` (shared ContextVar bridge),
  `_events.py` (shared EventBus + `default_bus` singleton), and the shared
  `StepKind` + `EventKind` enums. No pillar reaches into another pillar's
  internals.
- BYO LLM pattern across three pillars: `BYOLLMJudge` (Verifier),
  `BYOProvider` (Atlas), `BYOAutolearn` (Continuity) — all use the same
  `Callable[[str], str]` boundary.
- Observability / orchestration layers never raise from public surfaces.
  Structured outcomes (`DelegationResult`, `RoutingDecision`, `Verdict`, etc.)
  carry failure modes; calling code is never broken by a misbehaving
  observer.

### Tests + tooling

- 268 tests passing.
- `mypy --strict` clean across 57 source files.
- `ruff check` clean.
- Python 3.11+ required (uses `enum.StrEnum`).
- Zero runtime dependencies.
- Apache 2.0 licensed.

### Known limitations (deferred to Phase 2+)

- `Conductor.delegate` timeout uses `Thread.join` — the result is TIMEOUT but
  the thread keeps running. Use for soft deadlines only.
- `ToolRegistry` uses substring + tag matching; embeddings are Phase 2 via
  `pip install primal-ai[discovery]`.
- No first-party LLM caller. BYO LLM is the entire surface; first-party
  Howl ships Phase 2 as an optional extra.
- A2A v1.0 wire format is Phase 2.5; AgentCard is the precursor.
- MCP bridge is Phase 2.5.

[0.1.0]: https://github.com/primalaiagents/primal-core/releases/tag/v0.1.0
