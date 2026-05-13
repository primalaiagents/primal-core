# Guardian Roadmap (post-MVP)

The MVP Guardian (shipped Phase 1) covers six built-in policies, sync + async
wrappers, AllOf/AnyOf composition, a string DSL, and a dry-run mode. The
following are commercial differentiators deferred to Phase 2+ hardening.

## Phase 2 (M2 — hardening)
- [ ] OpenTelemetry spans on every policy check (sets up Trajectory handoff)
- [ ] Budget tracking across wrapped-agent lifetime (not just per-call)
- [ ] Decorator API: `@Guardian.guard(policies=[...])`
- [ ] `Not()` policy combinator
- [ ] Webhook escalation handler (POST violation to a URL)
- [ ] Structured violation IDs for cross-system correlation
- [ ] Policy versioning + migration helpers
- [ ] Performance budget: <1ms overhead per wrap call (benchmark suite)

## Phase 3+ (productization)
- [ ] Allowlist-by-default vs blocklist-by-default global modes
- [ ] Policy-as-config: YAML/TOML policy bundles
- [ ] Hot-reload policies without restart
- [ ] Multi-tenancy: per-tenant policy sets
- [ ] Audit log of every policy check (not just violations)
- [ ] Policy simulation: replay trajectories against new policies
- [ ] LLM-judge policy: "is this response safe per system prompt X?"

## Non-goals
- We don't lint agent CODE (that's static analysis territory)
- We don't sandbox agent EXECUTION (that's Verifier.sandbox territory)
- We don't decide WHICH model to call (that's Atlas territory)
