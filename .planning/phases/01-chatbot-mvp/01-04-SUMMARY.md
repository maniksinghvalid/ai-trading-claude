---
phase: 01-chatbot-mvp
plan: "04"
subsystem: backend/conversation-store
tags: [sqlmodel, sqlite, fastapi, rag, coreference, sessions, pytest, tdd]

dependency_graph:
  requires:
    - phase: 01-03
      provides: routes/chat.py POST /chat flow, llm_client.complete, schemas.py, conftest.py
  provides:
    - backend/src/session_store.py: Turn SQLModel + append_turn / history / list_sessions
    - backend/src/routes/sessions.py: GET /sessions + GET /sessions/{id}
    - backend/src/routes/chat.py: history-aware chat with coreference (modified)
    - backend/src/main.py: sessions router registered (modified)
    - backend/tests/test_session_store.py: 15 tests for store CRUD + coreference
  affects:
    - 01-05 (SSE streaming — chat.py append_turn pattern reused; stream route persists turns on completion)
    - 01-06 (frontend — GET /sessions + GET /sessions/{id} surfaced in session sidebar)

tech-stack:
  added:
    - sqlmodel>=0.0.22 (already in pyproject.toml; wired in session_store.py)
  patterns:
    - SQLModel Turn table with indexed session_id; create_all at module load (v0, no migrations)
    - Parameterized ORM queries only — no string-built SQL (T-04-02 mitigated)
    - Coreference: req.ticker=None -> inherit most recent non-null ticker_scope from history
    - History messages prepended to LLM messages list for multi-turn context
    - turn_index auto-incremented per session via MAX query (no separate sequence table)

key-files:
  created:
    - trading-chatbot/backend/src/session_store.py
    - trading-chatbot/backend/src/routes/sessions.py
    - trading-chatbot/backend/tests/test_session_store.py
  modified:
    - trading-chatbot/backend/src/routes/chat.py (history load + append_turn + coreference)
    - trading-chatbot/backend/src/main.py (sessions router registered)

key-decisions:
  - "Coreference via stored ticker_scope: req.ticker=None scans history reversed for most recent non-null ticker_scope and passes it to retrieve() — no LLM-based extraction (Phase 2 slice 6)"
  - "No-data path also persists both turns: user+assistant stored even when chunks=[] so session history is complete and a follow-up has prior context"
  - "turn_index computed as MAX existing + 1 in append_turn, not a DB sequence — avoids schema complexity while remaining correct for single-process Phase 1"
  - "datetime.now(timezone.utc) used instead of utcnow() to avoid Python 3.12 deprecation warning"
  - "list_sessions groups in Python after fetching all ordered turns — acceptable for single-user MVP; Phase 2 can push to SQL GROUP BY if session count grows"

requirements-completed: [CONV-01]

duration: ~15min
completed: 2026-06-08
---

# Phase 1 Plan 4: SQLite Conversation Store + Multi-Turn Coreference + /sessions Endpoints Summary

**SQLite-backed Turn model with coreference-aware /chat history and GET /sessions listing/detail — 33 tests pass including 15 new session-store tests.**

---

## Performance

- **Duration:** ~15 min
- **Started:** 2026-06-08
- **Completed:** 2026-06-08
- **Tasks:** 2 (1 TDD, 1 auto)
- **Files modified:** 5 (3 created + 2 modified)

---

## Accomplishments

- `session_store.py`: `Turn` SQLModel table with `id` (uuid PK), `session_id` (indexed), `turn_index` (int), `role` (str), `content` (str), `ticker_scope` (optional str), `created_at` (timezone-aware datetime). Engine bound to `settings.database_url`; `create_all` at module load (v0, no migrations). Three functions: `append_turn(session_id, role, content, ticker=None)` with auto-incrementing `turn_index` per session; `history(session_id, limit=20)` returning turns oldest-first; `list_sessions()` returning one entry per `session_id` with the first user message as title.
- `routes/sessions.py`: `GET /sessions` returns `list_sessions()`. `GET /sessions/{session_id}` returns the turn history as `[{role, content, created_at}]`.
- `routes/chat.py` (modified): loads `history(session_id, limit=10)` before retrieval; converts prior turns to OpenAI messages format (prepended to LLM call); coreference — when `req.ticker` is `None`, scans history reversed for most recent non-null `ticker_scope` and uses it for `retrieve()`; appends both user and assistant turns after every response (including no-data path). Session isolation is maintained — both the graceful no-data branch and the normal branch persist turns.
- `main.py` (modified): `sessions_router` included alongside `health_router` and `chat_router`.
- `tests/test_session_store.py`: 15 tests covering `append_turn`/`history` round-trip, `turn_index` ordering, `limit` capping, multi-session isolation, `ticker_scope=None`, `created_at` presence, `list_sessions` grouping + title selection, and three coreference inheritance scenarios. All use an in-memory SQLite fixture that replaces `ss.engine` via `monkeypatch`.
- Full suite: **33 passed, 5 skipped** (live-index tests skip without PINECONE_READ_KEY). All pre-existing `test_chat_endpoint.py` tests continue to pass.

---

## Task Commits (nested trading-chatbot repo)

| # | Task | Phase | Commit | Files |
|---|------|-------|--------|-------|
| RED | Failing session_store tests | TDD | `436c894` | tests/test_session_store.py |
| GREEN | session_store implementation | TDD | `f7fc832` | src/session_store.py |
| 2 | History-aware /chat + sessions routes + wire main | auto | `abd0106` | routes/chat.py, routes/sessions.py, main.py |

---

## Files Created/Modified

- `trading-chatbot/backend/src/session_store.py` — Turn SQLModel + append_turn / history / list_sessions
- `trading-chatbot/backend/src/routes/sessions.py` — GET /sessions + GET /sessions/{id}
- `trading-chatbot/backend/src/routes/chat.py` — history-aware RAG with coreference (modified)
- `trading-chatbot/backend/src/main.py` — sessions router registered (modified)
- `trading-chatbot/backend/tests/test_session_store.py` — 15 session store tests

---

## Decisions Made

- **Coreference via stored ticker_scope.** When a follow-up message arrives with no explicit ticker, the route scans history (reversed, limit 10) for the most recent non-null `ticker_scope` and uses that for Pinecone retrieval. This is a lightweight implementation requiring no LLM call; full ticker auto-extraction moves to Phase 2 slice 6.
- **No-data path persists both turns.** Even when `chunks=[]`, the user and assistant turns are appended to the session so the conversation history is complete. This ensures a follow-up in the same session has prior turns to inherit context from.
- **turn_index computed via MAX query.** Rather than a separate sequence table, `append_turn` queries for the last row by `turn_index DESC` and increments. Correct for single-process Phase 1; Phase 2 can migrate to a DB sequence if concurrent writers are added.
- **datetime.now(timezone.utc) instead of utcnow().** Avoids a Python 3.12 deprecation warning in the test output.

---

## TDD Gate Compliance

- RED commit `436c894`: `test(01-04): add failing tests for session_store` — 15 tests fail (ModuleNotFoundError — `src.session_store` not yet created). Gate passed.
- GREEN commit `f7fc832`: `feat(01-04): session_store — Turn SQLModel + append_turn / history / list_sessions` — 15 tests pass. Gate passed.

---

## Deviations from Plan

None — plan executed exactly as written. All acceptance criteria verified:
- `grep -c -E 'class Turn|def (append_turn|history|list_sessions)' session_store.py` == 4
- `index=True` and `create_all` present in session_store.py
- `history` import and 5 `append_turn` calls in routes/chat.py (import + 2 in normal path + 2 in no-data path)
- `sessions` referenced in sessions.py; sessions router included in main.py
- 15 session_store tests pass; all 33 offline tests pass

---

## Known Stubs

None. All functions are wired to real SQLite storage with no mock-data stubs.

---

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: sql_injection | `src/session_store.py` | All DB queries use SQLModel ORM parameterized queries — T-04-02 mitigated |
| threat_flag: stored_content | `src/routes/chat.py` | Stored turns treated as data; rendering escaped on frontend (slice 5) — T-04-03 mitigated |
| threat_flag: cross_session_read | `src/routes/sessions.py` | Single-user MVP — no auth/isolation; per-user scoping is Phase 2 AUTH-01 — T-04-01 accepted |

No new unmitigated threat surfaces introduced.

---

## User Setup Required

To verify the slice 3 Gate manually:

```bash
cd trading-chatbot/backend
# Start server (with .env populated):
uv run uvicorn src.main:app --reload

# Turn 1 — AAPL question:
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"bull case for AAPL","ticker":"AAPL"}' | python3 -m json.tool
# Note the session_id from the response.

# Turn 2 — coreference (no ticker, same session_id):
curl -s -X POST http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"what about the risks?","session_id":"<SESSION_ID_FROM_TURN_1>"}' | python3 -m json.tool
# Verify: response references AAPL without it being restated.

# Sessions list:
curl -s http://localhost:8000/sessions | python3 -m json.tool

# Session detail:
curl -s http://localhost:8000/sessions/<SESSION_ID_FROM_TURN_1> | python3 -m json.tool
```

---

## Self-Check: PASSED

Files confirmed on disk:
- trading-chatbot/backend/src/session_store.py: FOUND
- trading-chatbot/backend/src/routes/sessions.py: FOUND
- trading-chatbot/backend/src/routes/chat.py: FOUND (modified)
- trading-chatbot/backend/src/main.py: FOUND (modified)
- trading-chatbot/backend/tests/test_session_store.py: FOUND

Nested repo commits confirmed:
- 436c894: test(01-04): add failing tests for session_store — Turn CRUD + coreference
- f7fc832: feat(01-04): session_store — Turn SQLModel + append_turn / history / list_sessions
- abd0106: feat(01-04): history-aware /chat + GET /sessions endpoints + sessions router

pytest: 33 passed, 5 skipped (live-index tests skip without PINECONE_READ_KEY) — suite is green.

---

*Phase: 01-chatbot-mvp*
*Completed: 2026-06-08*
