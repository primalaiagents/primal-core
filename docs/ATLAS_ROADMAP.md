# Atlas Roadmap (post-MVP)

The MVP Atlas (shipped Phase 1, Sessions 7 + 8) covers provider registration,
capability/tag-based discovery, deterministic routing with health-aware
filtering, exponential-backoff cascade with cooldown, BYO provider integration,
Trajectory ROUTING_DECISION recording, **bandit-driven selection (Thompson
sampling + UCB1) with contextual partitioning and Storage-backed persistence**.
The following are deferred to Phase 2+.

## Phase 1 (DONE)
- [x] Bandit selection: Thompson sampling + UCB1 modes (Session 8)
- [x] Outcome learning: success/failure feeds back into provider weights (Session 8)
- [x] Contextual partitioning by ``bandit_context_key`` (Session 8)
- [x] Bandit state persistence via Storage Protocol (Session 8)

## Phase 2 (M2 — hardening)
- [ ] Async route() and invoke() (asyncio.wait_for cancellation)
- [ ] Per-provider rate limiting (Guardian integration)
- [ ] Cost budgets per route() / per session
- [ ] Provider warmup: probe health on registration
- [ ] OTel spans on every route + cascade attempt
- [ ] Streaming responses (when providers support it)

## Phase 2 (M2 — hardening) — bandit extensions
- [ ] Cost-aware bandit: reward = success * (1 - cost_normalized) — optimize for cheapest-that-works
- [ ] Latency-aware bandit: penalty term on slow arms
- [ ] Decay: older outcomes count less (exponentially weighted)
- [ ] LinUCB: linear contextual bandit when context is a feature vector, not a string key
- [ ] Auto-save on update with N-update batching
- [ ] Cross-process state via SQLite (today's persistence is single-process)

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
