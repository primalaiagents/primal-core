# PRIMAL Launch Draft

**Status:** banked, not shipped. Hold until 1.0 / Phase 2.5 (A2A v1.0 + MCP↔A2A bridge) lands. The story is stronger on a unique claim than on OTel as a feature.

**Channels (when ready):**
- Blog post on primalaiagents.com (canonical)
- X thread (links to blog)
- Show HN the morning after

**Pre-launch checklist:**
- [ ] PyPI token rotated
- [ ] At least 5 real users have tried PRIMAL and filed feedback
- [ ] Phase 2 hardening shipped (async, cron, embeddings, bandit decay)
- [ ] Phase 2.5 A2A v1.0 + MCP↔A2A bridge shipped
- [ ] README rewritten to match launch positioning
- [ ] primalaiagents.com landing page polished

---

## Blog post draft

**Title:** PRIMAL 0.2.1 — the library I wish I had when I started building agents

> Note: title and version references need updating when we actually ship. The "library I wish I had" frame holds across versions.

I spent the last six months building a personal AI assistant called KARIS. Eighty-nine plugins, seven hundred tools, multiple model providers, autonomous loops. Somewhere around plugin forty I stopped being able to tell what my own agent was doing when something went wrong.

I'd watch a request come in, watch a response come out, and the middle was a black box. Which model got picked? Why did Guardian let that tool call through? What was in the trajectory the last time this failed? I was writing print statements like it was 2010.

So I went looking for the framework that would solve this. LangChain felt like a stack of abstractions I'd have to unlearn before I could ship. The observability tools — LangSmith, Langfuse, Arize — all wanted my traces in their cloud, on their schema, for their monthly bill. For a hobby project. To watch my own code.

I built what I needed inside KARIS instead. Then I noticed the pieces I was building weren't KARIS-specific. They were the things any production agent needs and rarely has. So I pulled them out into their own library.

That library is **PRIMAL**, and 0.2.1 is now live on PyPI.

```bash
pip install primal-ai
```

**What you get, in one install:**

- **Guardian** — wrap any callable with policies. Rate-limit it, cap its cost, redact PII, validate I/O, gate dangerous actions.
- **Trajectory** — a black-box recorder for every agent run. Inputs, outputs, tool calls, errors, handoffs, all in one JSON-serializable record you can replay.
- **Verifier** — three-layer audit (rule-based, BYO LLM-judge, domain-specific). Returns `PASS / FAIL / UNCERTAIN` with reasons.
- **Conductor** — capability-based agent registry and delegation. AgentCard shapes map 1:1 to the A2A v1.0 wire format coming in Phase 2.5.
- **Atlas** — smart routing across providers, with health-aware filtering and opt-in bandit selection if you want it to learn.
- **Storage** — one Protocol, swappable backends. InMemory for tests, SQLite with WAL for production, Postgres and Redis reserved for Phase 2.
- **Harness** — health monitoring, tool registry, interval scheduler. Opt-in startup so importing the package never spawns a thread.
- **Continuity** — portable user profile with source, confidence, and three merge strategies. Your user memory, your file format.

And as of 0.2.1: **OpenTelemetry spans across all of it**, behind an optional `[otel]` extra. Pipe to Jaeger, Honeycomb, your own backend, or your terminal. No SaaS account. No proprietary dashboard. No telemetry tax on your hobby project.

```bash
pip install "primal-ai[otel]"
```

**What's deliberately not in PRIMAL:**

- No runtime dependencies. Stdlib-only at the core. The `[otel]` extra is the first optional dep we've ever shipped.
- No vendor coupling. Every LLM surface is a BYO `Callable[[str], str]`.
- No magic. The seven pillars compose through four named bridges at the package root — `_events`, `_trajectory_context`, `_jsonschema`, and the Storage Protocol — and otherwise stand alone.

**Where it came from:**

PRIMAL is extracted from KARIS, a production personal-AI system that's been running live since March. The donor codebase shaped every API. The pillars exist because I needed them, in that order, while building something real. Apache 2.0 — use it commercially.

**Where it's going:**

Phase 2 closes out hardening — async paths, cron syntax in the scheduler, embeddings-backed tool search, bandit decay. Phase 2.5 is A2A v1.0 compliance and the MCP↔A2A bridge nobody neutral has built yet. The roadmap lives in `docs/PRIMAL_ROADMAP.md` and I work on it in public.

If you've ever stared at your agent's output wondering *what just happened in there* — PRIMAL is what I wish I'd had then. Try it. Open issues. Star the repo if it resonates.

— Kunal
🐺 [primalaiagents.com](https://primalaiagents.com) · [github.com/primalaiagents/primal-core](https://github.com/primalaiagents/primal-core)

---

## X thread draft (8 tweets)

1/ I spent six months building a personal AI assistant called KARIS. Around plugin 40, I lost the ability to tell what my own agent was doing when things broke.

The observability tools wanted my traces in their cloud, on their schema, for a monthly bill. For a hobby project.

2/ So I pulled the reliability layer out of KARIS into its own library.

PRIMAL 0.2.1 is now live on PyPI:

`pip install primal-ai`

Stdlib-only at the core. Apache 2.0. Seven pillars + Storage. Built because I needed it.

3/ **Guardian** wraps any callable with policies — rate limit, cost cap, PII redaction, schema validation, gated dangerous actions.4/ **Trajectory** is a black-box recorder for every run. Inputs, outputs, tool calls, errors, handoffs — one JSON record you can replay.

**Verifier** audits the output. Rule-based, LLM-judge, or domain-specific. PASS / FAIL / UNCERTAIN with reasons.

5/ **Conductor** is capability-based agent-to-agent delegation. AgentCard maps 1:1 to A2A v1.0 in Phase 2.5.

**Atlas** routes across providers. Health-aware. Bandit selection is opt-in.

6/ **Continuity** is portable user memory with source + confidence + merge strategies. Your file format, not someone else's.

**Storage**, **Harness** round out the substrate.

7/ And new in 0.2.1: OpenTelemetry spans across all seven pillars.

`pip install "primal-ai[otel]"`

Pipe to Jaeger, Honeycomb, your own backend, your terminal. No SaaS. No dashboard rental.

8/ PRIMAL is what I wish I had when I started building agents.

If you've ever stared at your agent wondering *what just happened in there* — try it.

🐺 github.com/primalaiagents/primal-core

---

## Positioning notes

**Audience:** solo developers building AI agents in Python. Specifically: someone past "calling the OpenAI API in a script," with multiple tools/models/memory, whose codebase has gotten complex enough that they can't tell why things break. Working dev, any skill level. Frustrated emotional state when they find PRIMAL.

**One-liner (locked):**
> If you've ever stared at your agent's output wondering *what just happened in there*, PRIMAL is the observability layer that lets you find out — open-source, OpenTelemetry-native, no vendor required.

> Update before launch: at 1.0 / Phase 2.5, "observability layer" undersells. Likely rewrite as "the reliability and interoperability layer" matching README, or sharpen to a claim only PRIMAL can make (MCP↔A2A bridge).

**Phrases worth keeping:**
- "Telemetry tax on your hobby project" — names a frustration nobody else has named
- "Watch your own code" — sharp framing for the SaaS-observability objection
- "Print statements like it was 2010" — concrete, dates the pain
- "Plugin forty" — specific enough to be believable

**Phrases to revisit at launch time:**
- "Six months" → update to actual elapsed time
- "0.2.1" → update to actual launch version
- "Library I wish I had" → strong, but check that it still fits the actual feature surface at launch
