# Verifier Roadmap (post-MVP)

The MVP Verifier (shipped Phase 1) covers the three-layer architecture
(rule-based, LLM-judge surface, domain), a registry-based layer system,
shared JSON Schema validation, BYO-LLM integration, and trajectory-aware
verification. The following are deferred to Phase 2+ hardening.

## Phase 2 (M2 — hardening)
- [ ] First-party Howl: a built-in LLM judge that ships with the library
      behind an optional dep group: `pip install primal-ai[howl]`
- [ ] OpenAI-compatible Howl (works with OpenAI, Anthropic, Together, Ollama)
- [ ] Reverse-prompting: derive the goal from the output, judge against the
      derived goal (from KARIS production_auditor.py)
- [ ] Image verification: ImageReward-style aesthetic + alignment scoring
      (deferred — needs a deep-learning model)
- [ ] Code execution verifier: run claimed code in a sandbox, compare output
- [ ] DSL parser for verifier strings: `"json_schema:strict"`, `"regex:must=^OK"`
- [ ] Per-verifier cost budgets (mirrors Guardian's DollarCap)
- [ ] OTel spans on every verify() call

## Phase 3+ (productization)
- [ ] Verifier-as-config: YAML/TOML verifier bundles
- [ ] Verifier marketplace listings (Claw Mart)
- [ ] Differential verification: same trajectory through two verifier sets
- [ ] Active learning loop: failed verdicts become RuleBased rules
- [ ] Multi-judge ensembles with disagreement detection
- [ ] Replay-against-new-verifiers: re-grade old trajectories with new rules
- [ ] Reliability score aggregation across N trajectories per agent

## Non-goals
- We don't ship a first-party LLM caller in MVP (zero-dep constraint)
- We don't sandbox code execution (separate Verifier.sandbox surface, Phase 2+)
- We don't decide what the agent SHOULD have done — only whether it did what
  it claimed
- We don't replace the Verifier's verdict with an auto-fix (Guardian's
  escalation territory)
