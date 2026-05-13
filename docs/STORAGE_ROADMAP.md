# Storage Roadmap (post-MVP)

The MVP Storage layer (shipped Phase 1) covers InMemory (Session 1) and
SQLite (Session 4) backends behind a minimal Storage Protocol. The
following are deferred to Phase 2+ hardening.

## Phase 2 (M2 — hardening)
- [ ] PostgresStorage — asyncpg, connection pooling, JSONB column
- [ ] RedisStorage — async + sync clients, TTL support, pipelining
- [ ] TTL/expiry on the Storage Protocol (currently puts are forever)
- [ ] Migrations: schema versioning for SQLite
- [ ] Bulk operations: put_many / get_many / delete_many
- [ ] Storage events: emit on put/delete for cache invalidation downstream

## Phase 3+ (productization)
- [ ] Encryption-at-rest (transparent JSON encryption with per-namespace keys)
- [ ] Compression for large values (auto-zstd over a threshold)
- [ ] Sharding: hash-partition across N backends
- [ ] Read replicas + write-through caching
- [ ] S3 / object-storage backend for cold trajectories
- [ ] CDC stream (change-data-capture) for downstream consumers

## Non-goals
- We don't build a full ORM — Storage is intentionally key/value
- We don't query inside JSON values — that's a Postgres-feature when we get there, not a Protocol promise
- We don't ship a migration tool for cross-backend moves (separate concern)
