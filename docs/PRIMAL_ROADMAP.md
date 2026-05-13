# PRIMAL — Master Roadmap
## The Reliability & Interoperability Layer for AI Agents

> **Owner:** K (Karl as build partner)
> **Domain:** primalaiagents.com
> **Mascot:** Wolf with claw marks
> **Created:** May 2026
> **Status:** Pre-launch — extracting from KARIS Phase 56.5+
> **Doc version:** v1.1 (supersedes v1.0)
> **Major changes from v1.0:** Added Conductor pillar (A2A protocol), Atlas pillar (smart routing), Phase 2.5 for A2A compliance, continual learning under Continuity, production patterns library, components from KARIS that were missed (memory_autolearn, smart_router_logger, Tool RAG v2, Multi-Armed Bandit, Production Auditor, Talking-Head provider architecture).

---

## 0. How to use this document

Drop this MD file into any new Claude (Karl) session and say:

> "Karl, here's the PRIMAL roadmap v1.1. We're working on **[Phase X]**. Continuing from **[last completed item]**."

Karl will pick up with full context. Update the **Status Tracker** (Section 13) at the end of each session so we always know where we left off.

---

## 1. The Thesis

**PRIMAL is the reliability and interoperability layer for AI agents — vendor-agnostic, protocol-compliant, observable, verifiable.**

Three structural problems define the agent market in May 2026:

1. **Compound failure** — a 99% per-step success rate becomes 37% over 100 steps. Mathematical. Can't scale your way out.
2. **Opaque trajectories** — when an agent fails at hour 6 of an 8-hour run, you can't replay, root-cause, or trust it again.
3. **Interoperability gap** — Google's A2A protocol just shipped v1.0 in production at 150 organisations. Anthropic's MCP is the de facto tool standard with 18,000+ servers. **There is no formal MCP↔A2A bridge yet, and no observability/reliability layer that spans both.**

That third one is new since v1.0. It's also the most time-sensitive. PRIMAL ships the cross-protocol reliability layer before someone else owns it.

### The seven pillars (each maps to real, shipped KARIS components)

| Pillar | What it does | KARIS origin |
|---|---|---|
| **Guardian** | Validates every agent action before/after execution; policy enforcement | `karis_guardian.py` (959 lines, 14 workflow tests) |
| **Conductor** *(new)* | Agent-to-agent orchestration; A2A protocol compliance; MCP↔A2A bridge | `agent_bus.py` (922 lines, 5 pipeline templates, pub/sub) |
| **Trajectory** | Records, replays, root-causes agent failures; OTel-compatible | Agent Bus event system + `smart_router_logger.py` |
| **Continuity** | Portable user/project context graph + continual learning extraction | `karis_memory.db` schema + `memory_autolearn.py` |
| **Verifier** | Verifier toolkit (rule-based, LLM-judge, domain-specific) | `self_build_engine.py` + `production_auditor.py` (ImageReward + LLM-as-judge + reverse prompting) |
| **Atlas** *(new)* | Smart routing: multi-armed bandit, contextual scoring, cost optimization, cascade with failure cooldown | `model_router.py` (2,493 lines, 36 categories) + Talking-Head provider architecture (Phase 56.5) |
| **Harness** | Self-healing plugin system, scheduler, tool discovery at scale | `plugin_health.py` + `scheduler_v2.py` + `tool_rag.py` (ChromaDB, 741+ tools) |

This is why PRIMAL is buildable in 3-6 months: **you have ~7,000+ lines of production-tested code across these pillars already**. The work is extraction, hardening, productization, and standardization (A2A compliance) — not greenfield invention.

---

## 2. Product Surfaces

PRIMAL ships as **three connected products**, sold separately, more valuable together.

### 2.1 PRIMAL Core (SDK + Self-hosted)
The reliability layer as a Python library + Docker image. Drop it in front of any existing agent stack.

```python
from primal import Guardian, Conductor, Trajectory, Verifier, Atlas

agent = Guardian.wrap(my_existing_agent)
agent = Atlas.route(agent, providers=["claude", "gpt5", "gemini", "ollama"])

with Trajectory.record() as t:
    # Talks to other agents over A2A automatically
    result = Conductor.delegate(agent, task, peers=["billing_agent", "research_agent"])

if not Verifier.audit(result, t):
    Guardian.escalate(t)
```

- **License:** Apache 2.0
- **Pricing:** Free for OSS / <$1M ARR. Paid commercial license for >$1M ARR.
- **Target:** Indie devs, YC startups, internal platform teams.

### 2.2 PRIMAL Cloud (Hosted control plane)
Hosted SYNAQ — the "Datadog for AI agents." Customers send trajectory events; PRIMAL stores, indexes, visualizes, alerts. Also hosts A2A agent cards for discovery.

- **Pricing:** Usage-based ($0.001 per trajectory event, free tier 10K events/month).
- **Target:** Series A–C companies running agents in production.

### 2.3 PRIMAL Marketplace (Claw Mart)
Marketplace for verified, sandboxed agents/plugins. Every listing carries a PRIMAL reliability score (computed from real trajectory data). A2A-discoverable by any compliant agent in the world.

- **Pricing:** 15% take rate on transactions (when payments activate in Phase 5b).
- **Target:** Plugin authors, agent builders, end-user buyers.

The flywheel: **Core SDK ships free → trajectories flow to Cloud → reliability scores rank Marketplace listings → A2A-discoverable agents drive adoption back to Core.**

---

## 3. Six-Month Roadmap Overview

| Month | Phase | Theme | Outcome |
|---|---|---|---|
| **M1** | P1 | Extraction & Foundation | Core lib v0.1, repo public, landing page live |
| **M2** | P2 | Guardian + Trajectory MVP | First external alpha user finds a real bug with Guardian |
| **M2.5** | **P2.5** | **A2A Protocol Compliance** *(new)* | **PRIMAL speaks A2A v1.0 + hosts the MCP↔A2A bridge** |
| **M3** | P3 | Continuity + Verifier + Atlas | Cross-model context + smart routing + verifier toolkit live |
| **M4** | P4 | PRIMAL Cloud Beta | Hosted dashboard live, 10 paying customers, $1K MRR |
| **M5** | P5a | Marketplace Alpha (Discovery) | Claw Mart live, 20 verified A2A-discoverable listings |
| **M5.5** | P5b | Marketplace Payments | Stripe Connect live, first transactions flowing |
| **M6** | P6 | Commercial Launch | Public launch, $10K MRR, 1,000+ GitHub stars |

---

## 4. Phase 1 — Extraction & Foundation (Month 1, Weeks 1-4)

**Goal:** PRIMAL exists as a real repo with a real package, decoupled from KARIS, with a real landing page.

### 4.1 Repo & Package Setup
- [ ] Create GitHub org `primal-ai` (or `primalaiagents`)
- [ ] Create repos: `primal-core` (SDK, Apache 2.0), `primal-cloud` (backend, proprietary), `primal-inspector` (dashboard, MIT), `primal-web` (marketing), `primal-docs`
- [ ] Set up `pyproject.toml`, publish placeholder `primal` package to PyPI to claim the name
- [ ] Set up `primal-cli` entry point with subcommands: `init`, `inspect`, `publish`, `audit`

### 4.2 Brand & Landing Page
- [ ] Wolf-with-claw-marks logo (full mark + icon-only, SVG)
- [ ] Color palette + typography lockup
- [ ] Landing page at primalaiagents.com — hero, seven pillars, "drop into your agent stack" code example, A2A/MCP compliance badges, waitlist signup
- [ ] Tech stack: Next.js + Tailwind on Cloudflare Pages (you already use Cloudflare)
- [ ] Waitlist backed by Resend or Loops

### 4.3 Core Extraction (the surgical part)
Pull these from KARIS into clean, dependency-free modules:

| KARIS source | → | PRIMAL module |
|---|---|---|
| `karis_guardian.py` (959 lines) | → | `primal/guardian.py` |
| `agent_bus.py` (922 lines, pub/sub + pipelines) | → | `primal/conductor.py` + `primal/trajectory.py` |
| `memory_autolearn.py` | → | `primal/continuity/autolearn.py` |
| `karis_memory.db` schema | → | `primal/storage/sqlite.py` (+ Postgres, Redis, in-memory backends) |
| `self_build_engine.py` (902 lines) | → | `primal/verifier/sandbox.py` |
| `production_auditor.py` (ImageReward + LLM-judge) | → | `primal/verifier/domain.py` |
| `model_router.py` (2,493 lines) | → | `primal/atlas/` (router, bandit, cascade) |
| `tools/talking_head/` (Phase 56.5 cascade arch) | → | `primal/atlas/cascade.py` (generalized) |
| `plugin_health.py` | → | `primal/harness/health.py` |
| `scheduler_v2.py` | → | `primal/harness/scheduler.py` |
| `tool_rag.py` (ChromaDB hash persistence) | → | `primal/harness/discovery.py` |
| `smart_router_logger.py` | → | `primal/trajectory/logger.py` |
| `synaq.html` (1,235 lines) | → | `primal-inspector/` |

**Extraction principles (repeat every session):**
1. Strip every KARIS-specific name/import
2. No hard dependency on SQLite — pluggable `Storage` protocol (default SQLite, also Postgres, Redis, in-memory)
3. No hard dependency on Flask — framework-agnostic core
4. Zero references to ComfyUI, ElevenLabs, Twilio, YouTube, Razorpay, Suno, Remotion, FFmpeg
5. Type hints everywhere, `mypy --strict` passes
6. Tests for every public API before extraction is "done"
7. Preserve the WAL-mode-on-every-connection pattern (it's load-bearing)
8. Preserve the call-time API key pattern (the dotenv-timing-bug fix from Phase 53.1)

### 4.4 First Working Demo
- [ ] `primal init` CLI creates a starter project
- [ ] Wrap a toy 10-step agent with Guardian
- [ ] Show trajectory output in terminal and in browser inspector
- [ ] Record an asciinema demo for the landing page

### 4.5 Public Comms
- [ ] Twitter/X @primalaiagents
- [ ] First post: "Building the reliability layer for AI agents. A2A-native. MCP-bridged. Coming soon." + wolf logo
- [ ] LinkedIn post from K explaining the thesis

### 4.6 Phase 1 Exit Criteria
✅ `pip install primal` works
✅ Landing page live with waitlist
✅ One asciinema demo recorded
✅ 100 waitlist signups (organic — K's network + r/LocalLLaMA + HN comments, no paid)

---

## 5. Phase 2 — Guardian + Trajectory MVP (Month 2, Weeks 5-8)

**Goal:** A real external developer (not K) successfully wraps their agent with PRIMAL and finds a bug they wouldn't have caught otherwise.

### 5.1 Guardian Hardening
- [ ] Pre-execution validation: schema check, permission check, dangerous-action detection
- [ ] Post-execution validation: output schema, side-effect detection, drift detection
- [ ] **Pluggable policies** — `before_tool`, `after_tool`, `on_failure` hooks
- [ ] Built-in policy library: `no_external_network`, `no_filesystem_writes`, `dollar_amount_cap`, `pii_redaction`, `rate_limit`
- [ ] `Guardian.wrap()` adapters: LangChain, raw OpenAI tool-calling, Claude tool-use, custom loops

### 5.2 Trajectory Recording
- [ ] Capture every: tool call, tool result, LLM message, decision point, retry, failure
- [ ] Storage: local SQLite default, S3-compatible upload optional
- [ ] **Trajectory replay** — re-run a recorded trajectory deterministically (mock LLM with recorded responses)
- [ ] Trajectory diff — compare two runs of same task, surface what changed
- [ ] Export to OpenTelemetry format (enterprises already have OTel pipelines)
- [ ] Smart router logger pattern: every trajectory writes a human-readable `.md` summary alongside the structured event log

### 5.3 PRIMAL Inspector
- [ ] Fork SYNAQ dashboard into `primal-inspector` (MIT-licensed, runs locally)
- [ ] Rebrand from KARIS to PRIMAL (wolf, colors, copy)
- [ ] Strip KARIS-specific tabs (Dream Engine, Persona, etc.)
- [ ] Keep: trajectory timeline, failure root cause, tool call inspector, cost tracking
- [ ] Ship as `primal inspect` CLI command (auto-opens browser)
- [ ] Add cost tracking properly wired (the thing the KARIS SYNAQ build was missing per NEXT PRIORITIES item 7)

### 5.4 Documentation
- [ ] Quickstart (5 min): wrap an OpenAI agent
- [ ] Guide: writing custom Guardian policies
- [ ] Guide: trajectory replay for debugging
- [ ] Cookbook: wrapping LangChain, Claude tool-use, raw API calls, CrewAI, AutoGen
- [ ] Docs site on `docs.primalaiagents.com` (Mintlify or Docusaurus)

### 5.5 First Alpha Users
- [ ] Personally onboard 5 indie devs (DM on Twitter, 30-min Zoom)
- [ ] Private Discord channel for fast feedback
- [ ] Goal: 1 of 5 finds a real bug Guardian caught

### 5.6 Phase 2 Exit Criteria
✅ Guardian wraps 3+ agent frameworks
✅ Trajectory replay works for at least one realistic 50-step task
✅ 5 external alphas using it in real workloads
✅ 1 documented success story

---

## 6. Phase 2.5 — A2A Protocol Compliance (Month 2.5, Weeks 9-10) ⚡ TIME-CRITICAL

**Goal:** PRIMAL speaks Google A2A v1.0, hosts MCP servers for its own capabilities, and ships the missing MCP↔A2A bridge before anyone else does.

**Why this phase is urgent:** A2A v1.0 just shipped in production at 150 organisations (Google Cloud Next 2026, late April). No published spec exists yet for the MCP↔A2A bridge — but Google, Anthropic, and other AAIF members are working on it. If PRIMAL is the reference implementation when the spec drops, we own the layer.

### 6.1 A2A Agent Cards
- [ ] Implement `/.well-known/agent-card.json` for any agent wrapped by PRIMAL
- [ ] Agent Card schema: capabilities, supported tasks, pricing, reliability score, supported transports
- [ ] **The reliability score on the agent card is the differentiator** — no other agent platform exposes verified reliability data on discovery
- [ ] Card signing (DID-style) for trust verification

### 6.2 A2A Task Lifecycle
- [ ] Implement the full state machine: `submitted → working → input-required → completed | failed | canceled | rejected`
- [ ] Transport: HTTP + SSE + JSON-RPC 2.0 (no new protocol layer)
- [ ] Task delegation: PRIMAL agent can hand off to any A2A-compliant agent
- [ ] Task reception: external A2A agents can delegate to PRIMAL-wrapped agents

### 6.3 MCP Server Hosting
- [ ] Every PRIMAL capability exposes as an MCP server
- [ ] Auto-generate MCP server manifests from Guardian-wrapped agents
- [ ] Publish to MCP Registry (the Linux Foundation AAIF one) for discoverability
- [ ] Goal: appear in the 18,000+ indexed MCP servers as "PRIMAL Reliability Tools"

### 6.4 The Bridge (the part nobody's built)
- [ ] **MCP→A2A:** when an MCP tool invocation requires sub-agent delegation, automatically convert to A2A task
- [ ] **A2A→MCP:** when an A2A task receiver needs a tool the calling agent has, expose via MCP back-channel
- [ ] Trajectory captures both protocols in one timeline (this is the visualization win)
- [ ] Reference implementation, MIT-licensed, designed to be the spec when the spec exists

### 6.5 Conductor Module (Productizing Agent Bus)
- [ ] Pipeline templates extracted from KARIS (the 5 templates already shipped in Phase 48)
- [ ] Pub/sub event broadcast (already built in agent_bus.py)
- [ ] **A2A-native pipelines** — chain agents across organizational boundaries
- [ ] Failure isolation per-step (already proven in KARIS)

### 6.6 Public Positioning
- [ ] Blog post: "We built the MCP↔A2A bridge so you don't have to"
- [ ] Open RFC for community input on bridge spec
- [ ] Submit talk to Linux Foundation AAIF community meetings
- [ ] Reach out to Google A2A team (and Anthropic MCP team) for feedback

### 6.7 Phase 2.5 Exit Criteria
✅ PRIMAL agent successfully delegates to a non-PRIMAL A2A agent (e.g., a Workday or Salesforce partner agent from Google's 150-org list, if accessible; otherwise a test agent)
✅ PRIMAL MCP server listed in the AAIF registry
✅ Bridge demo: MCP tool call triggers A2A delegation, response flows back through MCP
✅ At least one mention from a recognizable name in the A2A/MCP community (DM, retweet, GitHub issue, whatever)

---

## 7. Phase 3 — Continuity + Verifier + Atlas (Month 3, Weeks 11-13)

**Goal:** Cross-model context portability with continual learning, verifier toolkit live, smart routing as standalone product.

### 7.1 Continuity Layer

**Portable User Format (PUF):**
- [ ] JSON schema: identity, preferences, project state, learned procedures, error history
- [ ] `primal.continuity.Profile` class — read/write a user's PUF
- [ ] Storage: local file, S3, Postgres — **encrypted-at-rest by default**
- [ ] Adapters to each provider's native format (Claude, GPT-5, Gemini, Ollama, Grok)

**Continual Learning (productizing memory_autolearn):**
- [ ] Auto-extract context from every trajectory (the memory_autolearn pattern, generalized)
- [ ] Procedure learning: when an agent solves a problem, extract the procedure → write to PUF → next call any model can use it
- [ ] **Distillation pipeline:** weekly summarize+compress accumulated context to prevent unbounded growth
- [ ] User-visible memory editor (let users see and edit what PRIMAL learned about them)

**The killer feature:** when one agent learns a user shortcut, *every other model the user runs gets it on the next call*. That's continual learning at the product layer, not the weight layer.

### 7.2 Verifier Toolkit

It's not one component — it's a *family*. Each verifier returns `{passed: bool, confidence: float, reasoning: str, suggested_fix: str?}`.

- [ ] **Rule-based verifier:** schema, regex, type checks — fast, free, no LLM
- [ ] **LLM verifier ("Echo"):** small model (Haiku/Gemini Flash/local 7B) judges actor output against task spec
- [ ] **Domain verifiers** (the Production Auditor pattern):
  - Image quality (ImageReward, ported from production_auditor.py)
  - Code correctness (test execution in sandbox, ported from self_build_engine.py)
  - Schema/SQL/JSON validation
  - LLM-as-judge for prose
  - Reverse prompting (reconstruct task from output, compare)
- [ ] **Custom verifier API** — users plug in domain-specific verifiers
- [ ] Cost target: verifier <5% of actor cost on average

### 7.3 Atlas (Smart Routing as a Product)

This is what KARIS's `model_router.py` becomes when extracted and productized. Sold separately as "the cost-optimization layer for any LLM stack."

- [ ] **Multi-armed bandit** across providers (epsilon-greedy, 30%→5% exploration decay)
- [ ] **Contextual scoring:** adaptive weights per category (reliability/speed/cost)
- [ ] **LLM classifier** (Gemini Flash Lite tier, ~$0.0001/call) determines category for every request
- [ ] **36+ task categories** (start with KARIS's, expand)
- [ ] **Cascade with failure cooldown** (the Talking-Head Phase 56.5 pattern, generalized): 3 fails in 60min → 5min skip; per-provider + per-tool stats
- [ ] **Selective tool sending:** non-Claude providers get only category-relevant tools (token savings)
- [ ] **Tool RAG v2** (ChromaDB with hash persistence) for tool discovery at scale — already proven at 741+ tools
- [ ] **Cost dashboard:** which provider, for which category, at what cost, with what reliability — *the enterprise selling point*

### 7.4 Reliability Scoring
- [ ] Every trajectory produces: `(steps_completed / total_steps) × (verifier_pass_rate) × (1 - human_intervention_rate)`
- [ ] Scores attached to: agent definition, user's PUF, trajectory record, **A2A agent card** (the discovery wedge)
- [ ] **Marketplace ranking signal** for Phase 5

### 7.5 Phase 3 Exit Criteria
✅ Same PUF tested with Claude + GPT-5 + Gemini + Ollama — all four return coherent personalized output
✅ Continual learning loop: agent A learns something, agent B inherits it within 1 hour
✅ Verifier catches 80%+ of intentionally-injected actor errors in test suite
✅ Atlas reduces cost on a benchmark workload by 30%+ vs single-provider baseline
✅ Reliability scores attached to all alpha agent cards
✅ 15 active alpha users

---

## 8. Phase 4 — PRIMAL Cloud Beta (Month 4, Weeks 14-17)

**Goal:** Hosted dashboard live, 10 paying customers at $99/month, $1K MRR.

### 8.1 Cloud Backend
- [ ] FastAPI on Railway (reuse Yeshua deployment playbook)
- [ ] Postgres for trajectory metadata, **Cloudflare R2** for trajectory blobs (already paying for it via Yeshua)
- [ ] Auth: Clerk or Supabase Auth (do NOT roll your own — Yeshua lesson)
- [ ] **Background-thread routing pattern** for long-running operations (the Phase 53.2 Cloudflare 120s timeout fix, productized)
- [ ] API endpoints:
  - `POST /trajectories` — ingest
  - `GET /trajectories/:id` — fetch
  - `GET /trajectories/:id/replay` — replay bundle
  - `GET /reliability/agents/:id` — score over time
  - `POST /alerts` — alert rules
  - `GET /agent-cards/:id` — public A2A card endpoint
  - `POST /a2a/tasks` — A2A task receiver
  - `GET /mcp/manifest` — MCP server manifest

### 8.2 Cloud Dashboard
- [ ] Next.js on Cloudflare Pages
- [ ] Views: Live trajectory feed, agent reliability leaderboard, failure heatmap, cost breakdown by provider (Atlas data), alert rules, billing
- [ ] Real-time updates via SSE
- [ ] Slack/Discord/email/webhook alerts on reliability drop or cost spike

### 8.3 SDK → Cloud integration
- [ ] `primal.configure(api_key="primal_...")` ships trajectories automatically
- [ ] Local-first mode still works (no Cloud account needed)
- [ ] Privacy mode: hash/redact payloads before upload (regex + LLM-based PII redaction)

### 8.4 Billing
- [ ] Stripe (reuse Yeshua patterns)
- [ ] Plans: **Indie $0** (10K events/mo), **Team $99** (1M events/mo), **Scale $499** (10M events/mo), **Enterprise** (custom)
- [ ] Usage metering + overage alerts BEFORE bill shock (people hate surprise bills)

### 8.5 Sales / Beta Outreach
- [ ] List of 50 targets: YC AI batch companies, A2A v1.0 partner orgs (the 150 from Google's announcement — public list), LangChain/CrewAI users, agent-product companies
- [ ] Personalized outreach (NOT cold spam) — DM founders, offer free 90 days
- [ ] Goal: 10 paying customers by end of M4

### 8.6 Phase 4 Exit Criteria
✅ cloud.primalaiagents.com live
✅ 10 paying customers
✅ $1K MRR
✅ One detailed case study published

---

## 9. Phase 5a — Marketplace Discovery (Month 5, Weeks 18-20)

**Goal:** Claw Mart live with 20 verified, A2A-discoverable listings. Discovery-first, not payments-first.

**Reframing from v1.0:** with A2A v1.0 in production, the immediate marketplace value is *discovery* — being the place developers find verified agents. Payments can ship in 5b.

### 9.1 Marketplace Architecture
- [ ] Listing schema: name, author, A2A agent card URL, MCP manifest URL, reliability score, supported models, pricing model
- [ ] **Every listing must pass PRIMAL Verifier before going live** — this is the moat
- [ ] Sandbox runner: Docker-isolated execution
- [ ] Categories: data extraction, content generation, research, ops automation, vertical (legal/medical/finance), video/creative
- [ ] **Every listing is auto-A2A-discoverable** — agents elsewhere on the network can find and delegate to marketplace agents

### 9.2 Publishing Flow
- [ ] `primal publish my-agent/` packages an agent
- [ ] Auto-runs verifier suite (catches malicious code, broken tools, hallucinated dependencies — the Self-Build Engine validation pattern)
- [ ] Manual review for first 50 listings (you + Karl), automated review after
- [ ] Author dashboard: listing stats, reliability trend, A2A invocation count

### 9.3 Discovery Flow
- [ ] Browse / search / filter by reliability score, category, model compatibility, price
- [ ] **Tool RAG-powered semantic search** (ChromaDB pattern, proven at 741+ tools) — type intent, get matching agents
- [ ] Try-before-buy: 100 free runs per listing
- [ ] One-click install into user's PRIMAL setup
- [ ] Reviews + reliability data shown side-by-side (reviews can lie; reliability data can't if it's auto-measured)

### 9.4 Seed the Marketplace
- [ ] Publish 5 KARIS-derived agents as flagship listings (anonymized — don't expose KARIS internals; only what's already in public KARIS phase notes is fair game)
- [ ] Recruit 15 alpha authors from existing user base + Discord
- [ ] **"PRIMAL Build Week" hackathon** — $5K in prizes for best listings

### 9.5 Phase 5a Exit Criteria
✅ market.primalaiagents.com live
✅ 20 verified A2A-discoverable listings
✅ At least 3 third-party authors
✅ Marketplace agents successfully invoked via A2A from outside PRIMAL

## 9.6 Phase 5b — Marketplace Payments (Weeks 20-21)
- [ ] Stripe Connect for author payouts
- [ ] Listings can be: free (lead-gen), paid one-time, subscription, per-run
- [ ] PRIMAL takes 15% of transactions
- [ ] **Exit criteria:** First $1K in marketplace GMV, at least 3 authors earning revenue

---

## 10. Phase 6 — Commercial Launch (Month 6, Weeks 22-24)

**Goal:** Public launch. Coordinated push. First $10K MRR.

### 10.1 Launch Prep (Weeks 22-23)
- [ ] Polish all docs, tutorials, videos
- [ ] 3-minute hero video (you on camera + screen capture, or fully animated)
- [ ] Launch essay: "The reliability layer for the agent era" — personal blog + LinkedIn + X
- [ ] Pre-brief 10 friendly press / creators (TechCrunch, The Information, Latent Space, MLST, Lenny's, swyx, simonw)
- [ ] Apply to YC Winter 2027 batch (check actual deadline — likely Aug-Sept 2026)
- [ ] Submit talk to Linux Foundation AAIF events

### 10.2 Launch Week (Week 24)
- **Monday:** Product Hunt launch
- **Tuesday:** Show HN
- **Wednesday:** Latent Space podcast (if booked)
- **Thursday:** AMA on r/LocalLLaMA + r/MachineLearning
- **Friday:** Recap, metrics, thanks

### 10.3 Post-Launch (ongoing)
- [ ] Monitor + respond to every comment, issue, DM
- [ ] Fix top 3 papercuts within 7 days
- [ ] Outreach to inbound enterprise leads
- [ ] Plan Q3 2026: enterprise tier, on-prem, SOC 2 path

### 10.4 Phase 6 Exit Criteria
✅ 1,000+ GitHub stars on primal-core
✅ 100+ paying Cloud customers
✅ $10K MRR
✅ 3+ press mentions
✅ Clear path to Series Seed (if raising) or to bootstrap to $50K MRR (if not)

---

## 11. Cross-Cutting Workstreams

These run in parallel across all phases.

### 11.1 Security & Trust
- [ ] Security audit before Phase 4 launch (paid, ~$5K)
- [ ] All trajectory data encrypted at rest and in transit
- [ ] PII redaction by default in Cloud
- [ ] SOC 2 Type 1 by month 9, Type 2 by month 18
- [ ] Bug bounty program (HackerOne or Intigriti) from Phase 4

### 11.2 Open Source Strategy
- [ ] Core SDK: Apache 2.0 (adoption flywheel)
- [ ] Inspector: MIT (gets embedded everywhere)
- [ ] MCP↔A2A bridge: MIT (designed to be the spec)
- [ ] Cloud + Marketplace: proprietary (that's the revenue)
- [ ] Contributor guidelines, CoC, issue templates from day 1
- [ ] "PRIMAL Champions" program — 10 high-signal contributors get free Cloud Scale tier

### 11.3 Production Patterns Library (NEW)

Ship the non-obvious production knowledge from KARIS as content + docs:
- [ ] **Pattern: Background-thread routing behind a reverse proxy** (Phase 53.2 Cloudflare timeout fix)
- [ ] **Pattern: Call-time API key reading** (Phase 53.1 dotenv timing bug)
- [ ] **Pattern: WAL mode on every SQLite connection** for concurrent agent writes
- [ ] **Pattern: Provider cascade with failure cooldown** (Phase 56.5 talking-head architecture)
- [ ] **Pattern: Parallel asset prefetch with ThreadPoolExecutor** (Phase 53.3, ~6 min → ~40s)
- [ ] **Pattern: Hash-persisted vector index** for fast restart (ChromaDB pattern)
- [ ] **Pattern: Hot-reload plugin system with circuit breaker** (plugin_health pattern, max 5 restarts)
- [ ] **Pattern: Selective tool sending** for non-Claude providers (token savings)
- [ ] **Pattern: Markdown trajectory logger alongside structured events** (smart_router_logger)
- [ ] **Pattern: Auto-detect and enforce style hints from content** (anime style enforcement → applies to any domain)

Each pattern: blog post + docs page + code example. This is SEO + community building + genuine product knowledge. Worth a chapter of every AI engineering book that gets written in 2027.

### 11.4 Community
- [ ] Discord server from Phase 2
- [ ] Weekly office hours (you + 30 min, Zoom or Discord stage)
- [ ] Monthly newsletter (changelog + community highlights + roadmap update)
- [ ] PRIMAL Pack — power-user community for top 100 contributors

### 11.5 Hiring (start thinking from Phase 3)
You can NOT do this alone for 6 months while still being a Casino Manager at sea. Plan:
- [ ] Month 3-4: Part-time backend engineer ($30-50/hr, 20 hrs/wk) — Cloud backend focus
- [ ] Month 5: DevRel/content (docs, videos, Discord)
- [ ] Month 6: Decide on full-time founding engineer if traction warrants

### 11.6 Capital
1. **Bootstrap** — fund from NCL salary + KARIS revenue. Slower, full ownership.
2. **YC W27** — apply Aug-Sept 2026, $500K for 7%. Distribution + credibility.
3. **Angels** — $250-500K from AI angels (swyx, simonw types, indie-leaning). Bridge to seed.

The A2A wedge makes (2) materially more attractive than it was in v1.0 — protocol-layer companies fit YC's thesis well.

---

## 12. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Foundation labs ship native reliability (OpenAI Eval++, Anthropic Workbench) | High | Medium | Vendor-agnostic by design. Their tools only work for their stack. |
| LangChain/LlamaIndex add reliability submodule | Medium | Medium | Move faster, integrate rather than compete |
| Google/Anthropic ship the MCP↔A2A bridge before us | High | High | **Speed.** Ship Phase 2.5 in M2.5 not M5. Be the reference impl when spec drops. |
| Market not ready — companies don't feel pain yet | Low (changed from v1.0) | High | A2A v1.0 at 150 orgs proves pain is here. Focus on those 150. |
| K's day job limits build hours | Certain | High | Hire part-time M3-4, ruthless scope cuts, kill features not deadlines |
| Open-core forked into commercial competitor | Low | Medium | Move fast on Cloud features needing server-side data accumulation |
| Privacy/compliance with trajectory data | Medium | High | Encryption + redaction + on-prem option from day 1 |
| Marketplace adverse selection (bad agents flood) | Medium | High | Verifier-gated listings, manual review first 50, reliability scoring as forcing function |
| A2A standard evolves and breaks our impl | Medium | Medium | Stay close to AAIF community; ship behind a compatibility shim |
| Competing protocols (ACP) gain ground | Low | Low | Support all three (MCP, A2A, ACP) — interop is the brand |

---

## 13. Status Tracker

**Single source of truth. Update at end of every session.**

```
PHASE: P1 — Extraction & Foundation
WEEK: 1 of 4
LAST COMPLETED: Trajectory MVP shipped (9 step kinds, replay, Guardian handoff, 59/59 tests). M2 demo path now functional end-to-end.
IN PROGRESS: —
BLOCKED ON: —
NEXT UP: Session 4 — Storage backends (SQLite first, Postgres + Redis to follow) OR Verifier MVP. Decide at session start.
WAITLIST: 0
GITHUB STARS: 0
MRR: $0
A2A AGENT CARD LIVE: NO
MCP SERVER LISTED IN AAIF REGISTRY: NO
```

---

## 14. Session Starter Templates

### 14.1 Generic session start
> Karl, here's the PRIMAL roadmap v1.1 (attached). We're working on **Phase [X]**, week **[N]**. Last session we finished **[item]**. Today let's tackle **[item]**.

### 14.2 Code session start
> Karl, PRIMAL session. Phase [X]. I need ready-to-drop-in files for **[component]**. Roadmap attached. Files I'm uploading: [list].

### 14.3 Strategy session start
> Karl, PRIMAL strategy session — no code today. I want to think through **[topic]**. Roadmap attached for context.

### 14.4 Sales/outreach session start
> Karl, PRIMAL outreach session. I need to draft [emails / DMs / launch post] for **[audience]**. Roadmap attached.

### 14.5 A2A/MCP protocol session start
> Karl, PRIMAL protocol session — Phase 2.5 work. Need to [implement spec / discuss bridge design / draft RFC]. Roadmap attached.

---

## 15. Decision Log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-11 | PRIMAL = reliability + interoperability layer (not just "agent platform") | Sharper wedge, harder to commoditize, KARIS internals cover 70%+ |
| 2026-05-11 | Open-core (Apache 2.0 SDK + MIT inspector + proprietary Cloud) | Adoption flywheel + revenue protection |
| 2026-05-11 | Wolf mascot, primalaiagents.com | Already secured |
| 2026-05-11 | 6-month timeline to commercial launch | Aggressive but doable given KARIS extraction shortcut |
| 2026-05-11 | **v1.1: Add Phase 2.5 — A2A Protocol Compliance** | A2A v1.0 in production at 150 orgs (Google Cloud Next 2026). No MCP↔A2A bridge spec yet. Time-critical wedge. |
| 2026-05-11 | **v1.1: Add Conductor pillar** | Agent-to-agent orchestration is a real product surface, not just a feature. Agent Bus is 80% of the primitive. |
| 2026-05-11 | **v1.1: Add Atlas pillar** | Smart routing (model_router.py) is enterprise gold. Cost optimization is the easiest enterprise pitch. |
| 2026-05-11 | **v1.1: Move marketplace from M5→M5a/5b** | Discovery before payments; A2A discoverability is the immediate value |
| 2026-05-11 | **v1.1: Production Patterns Library as content workstream** | 10 non-obvious production patterns from KARIS = SEO + community + genuine teaching value |
| 2026-05-11 | **v1.1: Continuity includes continual learning** (memory_autolearn) | Not just portable profile — extraction + distillation pipeline. Closer to continual learning frontier. |

---

## 16. Open Questions (resolve before Phase 1 ends)

1. **Pricing for indie tier** — $0 forever or $0 for 12 months then $19?
2. **Cloud region** — US-only at start, or US + EU from day 1?
3. **Naming for Verifier "Echo"** — keep or rebrand (Howl? Sentinel?)
4. **Marketplace name** — Claw Mart, Pack Market, or "Marketplace"?
5. **YC application** — apply W27 (Aug-Sept 2026 deadline) or skip and bootstrap?
6. **First hire** — backend eng or DevRel first?
7. **OSS license for Inspector** — MIT or Apache 2.0?
8. **Trajectory storage default** — local SQLite or always-on Cloud upload?
9. **A2A spec engagement** — try to drive the MCP↔A2A bridge spec officially via AAIF, or stay community-side and let the labs formalize?
10. **Voice/multimodal as v2** — Phase 6+ scope or separate product (the Wake Word + Voice Mode stack from KARIS is real)?
11. **Should the Self-Build Engine ship as its own product** ("the agent that builds agents")? It's distinct enough from Verifier to be its own surface.

---

## 17. KARIS Components Inventory (Extraction Reference)

Full source-to-target mapping for any extraction session. Keep this current.

```
KARIS (C:\KARIS\)                              PRIMAL (primal-core/)
├── karis_guardian.py (959 lines)        →    primal/guardian.py
├── agent_bus.py (922 lines)             →    primal/conductor.py + primal/trajectory.py
├── memory_autolearn.py                  →    primal/continuity/autolearn.py
├── self_build_engine.py (902 lines)     →    primal/verifier/sandbox.py
├── plugins/production_auditor.py        →    primal/verifier/domain.py (ImageReward + LLM-judge)
├── model_router.py (2,493 lines)        →    primal/atlas/router.py + atlas/bandit.py
├── tools/talking_head/ (Phase 56.5)     →    primal/atlas/cascade.py (generalized)
├── plugin_health.py                     →    primal/harness/health.py
├── scheduler_v2.py                      →    primal/harness/scheduler.py
├── tool_rag.py                          →    primal/harness/discovery.py
├── smart_router_logger.py               →    primal/trajectory/logger.py
├── plugin_loader.py                     →    primal/harness/loader.py
├── templates/synaq.html (1,235 lines)   →    primal-inspector/
└── karis_memory.db schema               →    primal/storage/sqlite.py
                                              + storage/postgres.py
                                              + storage/redis.py
                                              + storage/memory.py
```

**Components staying in KARIS (not extracted):**
- All YouTube/video pipeline (youtube_tool, video_styles, cinematic_engine, remotion-workspace, channel_manager)
- All voice/ElevenLabs/Whisper (specific to KARIS persona "Karl"/"Ivy")
- All Twilio/WhatsApp (specific to K's phone setup)
- Dream Engine (KARIS's overnight autonomous production)
- ComfyUI integration (image gen — domain-specific)
- Suno music integration
- Specific personas (Karl, Ivy, Andy, James voices)
- Yeshua, CrewWave integrations
- Any business-specific plugins (casino, maritime, anime channel logic)

**Extraction principles (every session):**
1. Strip every KARIS-specific name/import
2. Storage pluggable (no hard SQLite dep)
3. Framework-agnostic (no Flask dep)
4. Zero references to ComfyUI/ElevenLabs/Twilio/YouTube/Razorpay/Suno/Remotion
5. Type hints, `mypy --strict` passes
6. Tests for every public API
7. Preserve WAL-mode-everywhere pattern
8. Preserve call-time API key pattern
9. Preserve the markdown-logger-alongside-events pattern

---

## 18. The Wolf's Promise

PRIMAL exists because the agent era has three structural problems no foundation lab will solve horizontally:

1. **Reliability** — compound failure makes long-horizon agents fragile by default
2. **Interoperability** — A2A and MCP need a bridge, and no neutral party has built it
3. **Continuity** — every model sees a different fragment of the user

We solve all three. Vendor-agnostic. Protocol-compliant. Verifier-enforced. Observability-native.

**The wolf doesn't get locked in. The wolf works with any pack. The wolf is how the packs find each other.**

That's the brand. That's the bet. That's the next era.

---

*End of roadmap v1.1. Last updated: 2026-05-11. Update Section 13 (Status Tracker) every session.*
*v1.0 → v1.1 changelog in Section 15 Decision Log.*
