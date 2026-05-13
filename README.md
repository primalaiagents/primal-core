# 🐺 PRIMAL

**The reliability and interoperability layer for AI agents.**

> Status: Pre-alpha. Under active extraction from a production system. **Do not use in production yet.**

PRIMAL (`primal-ai`) is a Python package that makes any AI agent reliable, observable, and interoperable. A2A-native. MCP-bridged.

---

## Install

```bash
pip install primal-ai
```

> ⚠️ **Not yet published to PyPI.** Install from source until the first release.

```bash
git clone https://github.com/primalaiagents/primal-core
cd primal-core
pip install -e ".[dev]"
```

---

## Quick start

```python
from primal_ai import Guardian, Trajectory
from primal_ai.storage import SQLiteStorage

def my_agent(query: str) -> str:
    return f"results for {query!r}"

# Wrap any agent with PRIMAL's reliability layer
agent = Guardian.wrap(
    my_agent,
    policies=["no_external_network", "max_cost:$0.10/req"],
)

# Every action is recorded into an auditable Trajectory
with Trajectory.record(agent_id="search") as tr:
    tr.record_input({"query": "flights to tokyo"})
    result = agent("Find me a flight to Tokyo under $800")
    tr.record_output({"answer": result})

# Replay, audit, persist, or escalate on failure
print(tr.summary())

# Durable persistence — WAL-mode SQLite, no external dependencies
with SQLiteStorage("primal.db") as store:
    tr.save(store)
```

Audit the trajectory through any combination of verifier layers — rule-based,
LLM-judge (BYO model), or domain-specific (JSON Schema, regex, your own):

```python
from primal_ai import Verifier, JSONSchemaVerifier

verdict = Verifier.audit(
    tr,
    layers=[JSONSchemaVerifier(schema={"type": "object", "required": ["answer"]})],
)
print(verdict["status"])  # PASS / FAIL / UNCERTAIN
```

Route across providers (your wired-up models, APIs, or local agents). Atlas
ships health-aware selection + an exponential-backoff cascade; the bandit
learning layer arrives in Session 8.

```python
from primal_ai import Atlas, BYOProvider, Cascade, ProviderInfo

def good(task, **kw):  return f"OK: {task}"
def flaky(task, **kw): raise RuntimeError("upstream broke")

Atlas.register_provider(BYOProvider("primary", flaky, ProviderInfo(name="primary")))
Atlas.register_provider(BYOProvider("backup",  good,  ProviderInfo(name="backup")))

result = Cascade(providers=["primary", "backup"]).run("hello")
print(result.status.value, result.chosen)   # SUCCESS backup
```

Orchestrate agent-to-agent delegation and linear pipelines via Conductor.
Handoffs auto-record into the active Trajectory:

```python
from primal_ai import AgentCard, Capability, Conductor, Pipeline, PipelineStep

class Search:
    name = "search"
    card = AgentCard(name="search", description="...",
                     capabilities=(Capability(name="search", description="..."),))
    def invoke(self, input): return {"hits": [f"hit for {input}"]}

class Summarize:
    name = "summarize"
    card = AgentCard(name="summarize", description="...",
                     capabilities=(Capability(name="summarize", description="..."),))
    def invoke(self, input): return {"summary": f"summary of {input}"}

Conductor.register_agent(Search())
Conductor.register_agent(Summarize())
result = Pipeline(name="search-then-summarize", steps=[
    PipelineStep(name="find", agent_name="search"),
    PipelineStep(name="condense", agent_name="summarize"),
]).run("flights to tokyo")
print(result["_final"])
```

---

## The Seven Pillars

PRIMAL is built around seven composable pillars:

- **Guardian** — Policy enforcement and pre/post-execution validation. The first line of defense.
- **Conductor** — Multi-agent delegation, A2A messaging, and task routing.
- **Trajectory** — Structured "black box recorder" for every agent action; replay and audit.
- **Continuity** — Portable user profiles and auto-learned preferences across sessions and agents.
- **Verifier** — Output validation: rule-based, LLM-judge ("Howl"), and domain-specific.
- **Atlas** — Model + tool routing, multi-armed bandits, and failure-aware cascades.
- **Harness** — Health checks, scheduling, tool discovery (Tool RAG), and dynamic loading.

Each pillar can be used independently or composed into a full reliability stack.

---

## License

Apache 2.0 — see [LICENSE](./LICENSE).

---

## Status

This package is being extracted from a production system in phases. See the project roadmap (coming soon to this repo) for the full Phase 1–N plan and the KARIS extraction inventory.
