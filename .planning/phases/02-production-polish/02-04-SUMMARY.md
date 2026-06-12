---
phase: 02-production-polish
plan: "04"
subsystem: database
tags: [postgres, sqlmodel, docker-compose, audit-column, json-column]
dependency_graph:
  requires: ["02-03"]
  provides: ["Turn.retrieved_chunk_ids", "docker-compose-postgres", "switchable-database-url"]
  affects: ["session_store", "routes/chat", "tests/conftest"]
tech_stack:
  added: []
  patterns:
    - "SQLAlchemy Column(JSON) for cross-backend list storage"
    - "SQLModel create_all migration on first boot (no migration tool)"
    - "psycopg[binary] driver (already in locked stack)"
    - "postgres marker pattern (mirrors live_index auto-skip)"
key_files:
  created:
    - trading-chatbot/docker-compose.yml
    - trading-chatbot/backend/.env.example
  modified:
    - trading-chatbot/backend/src/session_store.py
    - trading-chatbot/backend/src/routes/chat.py
    - trading-chatbot/backend/tests/test_session_store.py
    - trading-chatbot/backend/tests/conftest.py
decisions:
  - "Column(JSON) via sa_column override makes list[str] work on both SQLite and Postgres without type-casting"
  - "docker-compose.yml omits version: attribute (Compose v2 considers it obsolete)"
  - "postgres marker auto-skip mirrors live_index pattern — one skip handler per marker in pytest_collection_modifyitems"
  - "Restart simulation uses two sequential create_engine calls on same temp-file URL (not in-memory — :memory: is connection-scoped)"
metrics:
  duration: "~15min"
  completed: "2026-06-09"
  tasks: 3
  files: 6
---

# Phase 2 Plan 04: Postgres Migration + retrieved_chunk_ids Audit Column Summary

Postgres-switchable database_url with a docker-compose Postgres service, an additive
`retrieved_chunk_ids` JSON audit column on `Turn`, and cross-backend parity tests — all
with zero behavioral change to the existing chat flow.

## What Was Built

### Task 1: Turn.retrieved_chunk_ids audit column (e8e2fef)

Added `retrieved_chunk_ids: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))`
to the `Turn` SQLModel table. `Column(JSON)` from SQLAlchemy is used as the `sa_column` override
so the list serializes as JSON on both SQLite and Postgres without any type-casting in application
code. `append_turn()` gained a `retrieved_chunk_ids=None` parameter.

`routes/chat.py` updated on both `/chat` and `/chat/stream` data paths:
```python
chunk_ids: list[str] = [c["id"] for c in chunks if c.get("id")]
append_turn(..., retrieved_chunk_ids=chunk_ids)
```
No-data path (both routes) leaves `retrieved_chunk_ids=None` — no change to that path.

Three new tests in `test_session_store.py`: round-trip of a list, None, and `[]`.

### Task 2: docker-compose Postgres + switchable database_url (0b09c6b)

`trading-chatbot/docker-compose.yml` with a `postgres:16-alpine` service:
- Credentials: `POSTGRES_DB=chatbot / POSTGRES_USER=chatbot / POSTGRES_PASSWORD=chatbot`
- Named volume: `pgdata:/var/lib/postgresql/data`
- Port: `5432:5432`
- Healthcheck: `pg_isready -U chatbot -d chatbot` (10s interval, 5s timeout, 5 retries)

`backend/.env.example` with commented Postgres DSN alongside the SQLite default:
```
DATABASE_URL=sqlite:///./chat.db
# DATABASE_URL=postgresql+psycopg://chatbot:chatbot@localhost:5432/chatbot
```

`config.py` unchanged — `database_url` already reads from env via pydantic-settings. Switching
requires only setting `DATABASE_URL` in the environment.

### Task 3: Cross-backend parity + postgres marker (168ce8e)

`conftest.py`: Added `postgres` marker with auto-skip when `DATABASE_URL` is absent or SQLite —
mirrors the `live_index` pattern for Pinecone.

`test_session_store.py`: Added `_run_full_turn_cycle(db_url)` helper that exercises the complete
`append_turn → history → list_sessions` cycle including `user_id` and `retrieved_chunk_ids` across
two sequential engines (restart simulation). Two tests use this helper:

- `test_cross_backend_parity_sqlite_restart_simulation`: temp-file SQLite (not `:memory:`, which
  is connection-scoped) proves schema migrates cleanly via `create_all` and sessions survive a
  simulated restart (offline, always runs).
- `test_cross_backend_parity_postgres_integration`: `@pytest.mark.postgres` — auto-skipped without
  a Postgres DSN; runnable locally against the compose stack.

## Verification Results

```
cd trading-chatbot/backend && uv run pytest
122 passed, 7 skipped (postgres + live_index markers), 1 warning
```

docker compose config: `COMPOSE_VALID` (no warnings after removing obsolete `version:` attribute).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed obsolete `version:` from docker-compose.yml**
- **Found during:** Task 2 verify
- **Issue:** `docker compose config -q` printed a deprecation warning about the `version:` attribute being obsolete in Compose v2
- **Fix:** Removed `version: "3.9"` line — Compose v2 does not require it and warns when present
- **Files modified:** `trading-chatbot/docker-compose.yml`
- **Commit:** 0b09c6b

### Out-of-Scope Items

None — all discovered issues were within scope of the current task's files.

## Known Stubs

None — all produced artifacts are wired end-to-end. `retrieved_chunk_ids` is populated from real `chunks` on the data path in both `/chat` and `/chat/stream`.

## Threat Flags

No new threat surface introduced beyond what the plan's threat model covers:
- T-02-04-01 (credentials in env/compose only): `.env` remains in `.gitignore`; docker-compose.yml uses defaults safe for local dev only
- T-02-04-02 (SQL injection): all access remains via SQLModel ORM — no string-built SQL added
- T-02-04-SC (no new packages): psycopg[binary] was already in the locked stack; `Column` and `JSON` come from SQLAlchemy which is a SQLModel transitive dependency

## Self-Check

- [x] `trading-chatbot/docker-compose.yml` created and validated
- [x] `trading-chatbot/backend/.env.example` created
- [x] `session_store.py` has `retrieved_chunk_ids` column
- [x] `routes/chat.py` populates chunk_ids on data path (both /chat and /chat/stream)
- [x] `test_session_store.py` has 3 new audit column tests + 2 new parity tests
- [x] `conftest.py` has postgres marker + auto-skip handler
- [x] All 3 tasks committed individually to trading-chatbot repo
- [x] `uv run pytest`: 122 passed, 7 skipped
