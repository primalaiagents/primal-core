# Continuity Roadmap (post-MVP)

The MVP Continuity (shipped Phase 1) covers UserProfile with confidence/source
metadata, three merge strategies, BYO-LLM autolearn, Storage-backed persistence,
and PROFILE_UPDATED events. The following are deferred.

## Phase 2 (M2 — hardening)
- [ ] First-party autolearn: ships behind `pip install primal-ai[autolearn]`
      with OpenAI-compatible LLM client
- [ ] Per-field TTL / expiry (some preferences are temporary)
- [ ] Profile diffing: compare two profiles, emit a structured change set
- [ ] Profile versioning + migrations
- [ ] OTel spans on autolearn extract calls
- [ ] Cross-agent profile sync via A2A (delegate carrying user profile)
- [ ] PII redaction at save time (configurable per-field)

## Phase 3+ (productization)
- [ ] Portable User Format (PUF) export: standardized JSON schema for cross-vendor
      profile portability
- [ ] Consent rules: per-field, per-agent access controls
- [ ] Multi-device sync (PRIMAL Cloud)
- [ ] Conflict resolution UI (Inspector) for human-in-the-loop merges
- [ ] Embedding-based profile search (find similar users for cold-start agents)

## Non-goals
- We don't ship a first-party autolearn body in MVP (zero-dep constraint)
- We don't make policy decisions on behalf of the user — Continuity stores facts;
  Guardian enforces rules over them
- We don't model the user — Continuity persists declared preferences, not inferred
  ones beyond what BYOAutolearn extracts
