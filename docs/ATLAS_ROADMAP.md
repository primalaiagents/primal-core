# Atlas Roadmap (post-MVP)

The MVP Atlas core (shipped Phase 1 Session 7) covers provider registration,
capability/tag-based discovery, deterministic routing with health-aware
filtering, exponential-backoff cascade with cooldown, BYO provider integration,
and Trajectory ROUTING_DECISION recording. The bandit learning layer ships in
Session 8. The following are deferred to Phase 2+.

## Phase 1 Session 8 (next)
- [ ] Bandit selection: Thompson sampling + UCB1 modes
- [ ] Outcome learning: success/failure/cost feeds back into provider weights
- [ ] Contextual scoring: capability + cost + latency hints affect ranking
- [ ] Bandit state persistence via Storage Protocol

## Phase 2 (M2 — hardening)
- [ ] Async route() and invoke() (asyncio.wait_for cancellation)
- [ ] Per-provider rate limiting (Guardian integration)
- [ ] Cost budgets per route() / per session
- [ ] Provider warmup: probe health on registration
- [ ] OTel spans on every route + cascade attempt
- [ ] Streaming responses (when providers support it)

## Phase 3+ (productization)
- [ ] First-party provider adapters as optional installs:
      pip install primal-ai[openai|anthropic|gemini|ollama|groq]
- [ ] Provider marketplace listings (Claw Mart)
- [ ] Multi-region routing (latency-aware)
- [ ] Failover policies: primary/secondary/tertiary tiers
- [ ] Provider negotiation (price discovery via A2A)
- [ ] Cost forecasting: estimate session cost before invoke()

## Non-goals
- We don't ship first-party HTTP clients to any LLM (zero-dep constraint)
- We don't decide what an agent SHOULD do — only which provider executes the task
- We don't replace Guardian's policy enforcement at the provider layer
- We don't implement provider-side caching (that's an upstream caller concern)
