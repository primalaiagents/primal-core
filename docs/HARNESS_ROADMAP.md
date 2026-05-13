# Harness Roadmap (post-MVP)

The MVP Harness (shipped Phase 1) covers health monitoring, tool registry
(substring/tag search), and interval-based scheduling with EventBus
integration. The following are deferred.

## Phase 2 (M2 — hardening)
- [ ] Cron syntax for scheduled jobs (5-field cron + every-N-units sugar)
- [ ] Job persistence: save/restore scheduler state via Storage
- [ ] Async scheduler path (asyncio-based Scheduler variant)
- [ ] Tool embeddings: optional `pip install primal-ai[discovery]` adds ChromaDB
      semantic search over tool descriptions
- [ ] Plugin hot-reload: watch a tools directory, register/unregister on change
- [ ] OTel spans on scheduled job runs + health checks
- [ ] Distributed scheduler: lease-based job ownership across N workers

## Phase 3+ (productization)
- [ ] MCP tool discovery: walk MCP servers, surface their tools as ToolInfo
- [ ] Tool sandbox: run tools in resource-isolated subprocess
- [ ] Tool reputation: aggregate Verifier verdicts per-tool, expose as score
- [ ] Self-healing: failed health checks trigger configured remediation actions

## Non-goals
- We don't decide WHICH tool gets called — that's Atlas + Conductor's territory
- We don't ship a workflow engine — Conductor.Pipeline is the orchestration surface
- We don't run user code in sandboxes (Phase 2+); MVP runs in-process
