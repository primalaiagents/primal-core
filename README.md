# 🐺 PRIMAL

> **The reliability and interoperability layer for AI agents.**

[![PyPI version](https://img.shields.io/pypi/v/primal-ai.svg)](https://pypi.org/project/primal-ai/)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Tests](https://img.shields.io/badge/tests-268%2F268-brightgreen.svg)](#)

PRIMAL (`primal-ai`) wraps any AI agent with the seven things production
agents need but rarely have: policy enforcement, structured recording,
output verification, multi-agent orchestration, smart routing, durable
persistence, and portable user memory. Zero runtime dependencies. A2A
AgentCard precursor shape. MCP bridge surface ready for Phase 2.5.

---

## Install

```bash
pip install primal-ai
```

Requires Python 3.11+. No other runtime dependencies — PRIMAL ships
stdlib-only.

---

## 60-second example

The example below uses all seven pillars + Storage in a single flow:
wrap an agent with Guardian, make it discoverable to Conductor + Atlas +
Harness, then record, persist, audit, and remember in one durable loop.
It runs end-to-end against fake agents — no API keys, no network.

```python
from primal_ai import (
    Atlas, BYOProvider, ProviderInfo, ThompsonBandit,
    Conductor, AgentCard, Capability,
    Continuity, Guardian, Harness,
    JSONSchemaVerifier, ToolInfo, Trajectory, Verifier,
)
from primal_ai.storage import SQLiteStorage

# 1. Any callable becomes an agent — wrap it with Guardian's policies.
def search_agent(query: str) -> dict:
    return {"answer": f"results for {query!r}"}

agent = Guardian.wrap(search_agent, policies=["no_external_network", "max_cost:$0.10/req"])

# 2. Make the agent + tools + providers discoverable.
class SearchAgent:
    name = "search"
    card = AgentCard(name="search", description="search the web",
                     capabilities=(Capability(name="search", description="..."),))
    def invoke(self, q): return search_agent(q)

Conductor.register_agent(SearchAgent())
Harness.register_tool(ToolInfo(name="search", description="search the web", tags=("web",)))
Atlas.register_provider(BYOProvider(
    name="echo",
    call=lambda task, **kw: f"OK: {task}",
    info=ProviderInfo(name="echo", capabilities=("chat",)),
))
Atlas.set_selector(ThompsonBandit(seed=42))  # opt-in: learn from outcomes

# 3. Record, persist, audit, remember.
with SQLiteStorage("primal.db") as store:
    with Trajectory.record(agent_id="search") as tr:
        tr.record_input({"query": "flights to tokyo"})
        tr.record_output(agent("Find flights to Tokyo under $800"))
    tr.save(store)

    verdict = Verifier.audit(tr, layers=[
        JSONSchemaVerifier(schema={"type": "object", "required": ["answer"]}),
    ])
    print("verdict:", verdict["status"])  # PASS

    Continuity.update("user-k", "language", "en", source="user", store=store)
```

---

## The seven pillars (plus Storage)

**Guardian** — Policy enforcement. Wraps any callable with pre/post checks
that gate dangerous actions, redact PII, cap dollar cost, rate-limit
calls, and validate input/output schemas. Composes via `AllOf` /
`AnyOf` and is configurable via a compact string DSL. Violations route
through a pluggable escalation handler.
```python
agent = Guardian.wrap(my_agent, policies=["rate_limit:per_minute=60", "max_cost:$0.10/req"])
```

**Trajectory** — Structured "black box recorder" for every agent
execution. Captures inputs, outputs, tool calls, LLM calls, errors,
retries, and inter-agent handoffs into a JSON-serializable record.
Replay, filter by step kind, or persist via the Storage Protocol.
```python
with Trajectory.record(agent_id="search") as tr:
    result = agent(query)
```

**Verifier** — Three-layer audit framework: rule-based, BYO LLM-judge,
and domain-specific. Returns a `Verdict(PASS | FAIL | UNCERTAIN)` with
confidence + reasons. JSONSchemaVerifier and RegexMatchVerifier ship
built-in; BYOLLMJudge is the LLM surface (you supply the model call).
```python
verdict = Verifier.audit(tr, layers=[JSONSchemaVerifier(schema=...)])
```

**Conductor** — Agent-to-agent orchestration. Capability-based agent
registry, single-hop delegation with REFUSED/FAILED/TIMEOUT outcomes,
linear pipelines, and a sync pub/sub EventBus. AgentCard field names
are chosen so a Phase 2.5 serializer maps 1:1 to A2A v1.0.
```python
Conductor.register_agent(my_agent_instance)
```

**Atlas** — Smart routing across providers (your wired-up models, APIs,
or local agents). Provider Protocol, BYOProvider, capability/tag-based
discovery, health-aware filtering, exponential-backoff cascade. Opt
into bandit-driven selection (Thompson sampling or UCB1) when you
want learning; deterministic routing stays the default.
```python
name, result = Atlas.invoke("task", context={"capability": "chat"})
```

**Storage** — Pluggable persistence behind one Protocol. InMemory for
tests; SQLite for production (WAL mode, JSON values, thread-safe per
connection, strict at the boundary). Postgres + Redis stubs reserved
for Phase 2. The Protocol is what every pillar persists through.
```python
with SQLiteStorage("primal.db") as store: tr.save(store)
```

**Harness** — Runtime substrate: health monitoring, tool registry
(substring + tag, no embeddings), and an interval-based scheduler.
Opt-in startup so importing the package never spawns a background
thread.
```python
Harness.register_tool(ToolInfo(name="search", description="...", tags=("web",)))
```

**Continuity** — Portable user profile with explicit source + confidence
metadata, three merge strategies (`self` / `other` / `higher_confidence`),
and BYO autolearn for extracting facts from text via your model. Storage-
backed persistence.
```python
profile = Continuity.update("user-k", "language", "en", source="user", store=store)
```

---

## Architecture

The seven pillars compose through small, named neutral primitives at the
package root — no pillar reaches into another's internals:

```
primal_ai/
├── _events.py             # shared EventBus + default_bus singleton (Conductor + Atlas + Harness + Continuity publish here)
├── _trajectory_context.py # ContextVar bridge — Trajectory sets, Conductor + Atlas read
├── _jsonschema.py         # shared subset validator (Guardian SchemaValidator + Verifier JSONSchemaVerifier)
├── guardian/              ← policy enforcement
├── trajectory/            ← causal recording
├── verifier/              ← output audit
├── conductor/             ← multi-agent orchestration
├── atlas/                 ← provider routing
├── storage/               ← persistence
├── harness/               ← runtime substrate
└── continuity/            ← portable user memory
```

Three pillars expose a **BYO LLM** surface — `BYOLLMJudge` (Verifier),
`BYOProvider` (Atlas), `BYOAutolearn` (Continuity) — all using the same
`Callable[[str], str]` boundary. A first-party LLM caller will ship as
an optional install in Phase 2; the MVP stays dependency-free.

---

## Why PRIMAL?

- **Zero runtime dependencies.** Stdlib-only. No supply chain risk, no
  version pin headaches.
- **Extracted from a production system.** Donor codebase is KARIS — 89
  plugins, 700+ tools, live since March 2026. PRIMAL keeps the DNA and
  drops the vendor coupling.
- **A2A-friendly out of the box.** AgentCard, Capability, and
  ProviderInfo shapes are designed so a Phase 2.5 serializer can map
  them 1:1 to A2A v1.0 wire format without renames.
- **Composable, not monolithic.** Use one pillar or all eight. They
  share four small, named bridges at the package root and otherwise
  stand alone.
- **Apache 2.0 licensed.** Use it commercially.

---

## Status

This is **0.1.0** — the first public release. All seven pillars shipped
as MVPs across nine focused sessions in two weeks. 268 tests passing,
`mypy --strict` clean, `ruff check` clean.

- **Phase 2 (M2 — hardening)** ships OTel spans, async paths, first-party
  LLM judges as an optional extra, cron syntax in the scheduler,
  embeddings-backed tool search, and bandit decay.
- **Phase 2.5** ships A2A v1.0 wire format compliance and the MCP↔A2A
  bridge that no neutral party has built yet.

See [`docs/PRIMAL_ROADMAP.md`](./docs/PRIMAL_ROADMAP.md) for the full
plan and [`CHANGELOG.md`](./CHANGELOG.md) for what shipped in 0.1.0.

---

## Links

- **GitHub:** https://github.com/primalaiagents/primal-core
- **Issues:** https://github.com/primalaiagents/primal-core/issues
- **Roadmap:** [`docs/PRIMAL_ROADMAP.md`](./docs/PRIMAL_ROADMAP.md)
- **Per-pillar roadmaps:** [`docs/`](./docs/) (one file per pillar)

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).
