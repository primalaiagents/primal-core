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

# Wrap any agent with PRIMAL's reliability layer
agent = Guardian.wrap(
    my_agent,
    policies=["no_external_network", "max_cost:$0.10/req"],
)

# Every action is recorded into an auditable Trajectory
with Trajectory.record(agent_id="search") as tr:
    result = agent("Find me a flight to Tokyo under $800")

# Replay, audit, or escalate on failure
print(tr.summary())
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
