---
phase: 01-chatbot-mvp
plan: "05"
subsystem: backend/sse-streaming
tags: [sse, fastapi, openai, streaming, pytest, sse_starlette]

dependency_graph:
  requires:
    - phase: 01-04
      provides: routes/chat.py POST /chat flow, session_store append_turn/history, llm_client.complete
  provides:
    - backend/src/llm_client.py: stream_complete(system, messages) generator over OpenAI streaming deltas
    - backend/src/routes/chat.py: POST /chat/stream SSE endpoint emitting session/citations/token*/done
    - backend/tests/test_chat_stream.py: 13 tests for event order, citations-once, turn persistence, error handling
  affects:
    - 01-06 (frontend — ChatWindow consumes session/citations/token/done events from /chat/stream)

tech-stack:
  added:
    - sse-starlette>=2.1 (already declared; wired in routes/chat.py via EventSourceResponse)
  patterns:
    - Sync generator over OpenAI stream=True deltas; wrapped in LLMProviderError on any API error
    - Async generator inside EventSourceResponse; yields dicts with event+data keys
    - Temp-file SQLite in tests (not in-memory) — SQLite :memory: is connection-scoped; sse_starlette ASGI runner opens connections from worker threads and would see an empty DB

key-files:
  modified:
    - trading-chatbot/backend/src/llm_client.py (stream_complete generator added)
    - trading-chatbot/backend/src/routes/chat.py (POST /chat/stream SSE endpoint added)
  created:
    - trading-chatbot/backend/tests/test_chat_stream.py (13 streaming tests)

key-decisions:
  - "Temp-file SQLite in streaming tests: SQLite :memory: databases are connection-scoped — each connection opens an empty DB. sse_starlette runs the async generator in anyio worker threads that open their own connections, so in-memory never works for cross-thread access. Temp file with check_same_thread=False is visible to all connections."
  - "Sync generator for stream_complete: OpenAI's streaming API is synchronous (httpx-based); the generator is consumed inside the async _event_generator via a synchronous for-loop (FastAPI runs sync routes in thread pool anyway)."
  - "Mid-stream error path emits error event then done without leaking key/stack trace (T-05-02): LLMProviderError message is the generic 'LLM provider unavailable' — the same sanitized text used in /chat's 503 response."
  - "Citations serialized once up front before any token: matches the locked event order in 01-CONTEXT.md; frontend can render the source list before the full response arrives."

requirements-completed: [STREAM-01]

duration: ~20min
completed: 2026-06-08
---

# Phase 1 Plan 5: SSE Streaming — stream_complete + POST /chat/stream Summary

**OpenAI token-streaming generator and SSE endpoint emitting session/citations/token*/done in order — 46 tests pass (13 new + 33 pre-existing), 5 skipped (live-index).**

---

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-08
- **Completed:** 2026-06-08
- **Tasks:** 2 (both auto)
- **Files modified:** 2 (modified) + 1 (created)

---

## Accomplishments

- `llm_client.py` (modified): Added `stream_complete(system, messages) -> Generator[str, None, None]`. Calls OpenAI Chat Completions with `stream=True`, yields each non-empty `chunk.choices[0].delta.content`. Wraps both pre-stream errors (before iteration starts) and mid-stream errors (during iteration) in `LLMProviderError` so the SSE route can emit a safe terminating error event without leaking key material or stack traces (T-05-02). `complete()` is completely unchanged.

- `routes/chat.py` (modified): Added `POST /chat/stream` via `sse_starlette.EventSourceResponse`. The inner `_event_generator` async generator:
  1. Resolves `session_id` (mint or use supplied) → emits `event: session`
  2. Loads prior history, applies coreference (same logic as `/chat`)
  3. Retrieves chunks (k=6) — Pinecone failure degrades gracefully to `chunks=[]`
  4. Builds citations from real chunk metadata only (T-05-03) → emits `event: citations` ONCE up front
  5. No-data path: emits graceful message as single token, persists both turns, emits `event: done`
  6. Normal path: iterates `stream_complete`, emits `event: token` per delta, buffers full text
  7. On completion: `append_turn` for user and assistant → emits `event: done`
  8. Mid-stream `LLMProviderError` → emits `event: error` (generic message only) then `event: done`

- `tests/test_chat_stream.py` (created): 13 tests covering event order (session→citations→token*→done), citations emitted exactly once before any token, token payloads carry exact content including leading-space tokens, both turns persisted on completion, persisted turns queryable via GET /sessions/{id}, no-data path emits graceful token + persists turns, LLM error emits error+done without key leakage, session ID passthrough and new UUID4 minting, citations content from real metadata. Uses temp-file SQLite engine fixture to avoid SQLite connection-scoping issues with sse_starlette's async runner.

---

## Task Commits (nested trading-chatbot repo)

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | stream_complete generator | `6a63e98` | src/llm_client.py |
| 2 | POST /chat/stream + 13 tests | `78c9c54` | src/routes/chat.py, tests/test_chat_stream.py |

---

## Files Created/Modified

- `trading-chatbot/backend/src/llm_client.py` — stream_complete generator added; complete() unchanged
- `trading-chatbot/backend/src/routes/chat.py` — POST /chat/stream SSE endpoint added
- `trading-chatbot/backend/tests/test_chat_stream.py` — 13 streaming tests (all pass)

---

## Decisions Made

- **Temp-file SQLite for streaming tests.** SQLite `:memory:` databases are connection-scoped: every new connection to `sqlite:///:memory:` opens a fresh empty database. sse_starlette's ASGI runner iterates the async generator from within anyio's worker thread pool, opening new connections that cannot see the tables created by the test's in-memory engine. Switching to a temp file (with `check_same_thread=False`) makes the schema visible to all connections and matches how `test_session_store.py` works implicitly (its `autouse` fixture was the same pattern but bypassed the cross-thread issue by not using the ASGI runner).

- **Sync generator for stream_complete.** The OpenAI Python SDK's streaming API is synchronous (built on httpx); using a sync generator keeps the implementation simple and avoids `async for` semantics. Inside `_event_generator` the `for token in stream_complete(...)` call runs inline in the async context — FastAPI runs sync route handlers (including sync generators) on the thread pool, so blocking is not a concern for single-user Phase 1.

- **`event: error` then `event: done` on mid-stream LLM failure.** The threat model (T-05-02) requires that mid-stream provider errors emit a terminating safe message without leaking the API key or a Python traceback. Emitting `error` then `done` allows the frontend (slice 5) to detect the failure and render a graceful message while closing the stream cleanly.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SSE parser stripped leading spaces from token data**
- **Found during:** Task 2 tests
- **Issue:** `_parse_sse_events` applied `.strip()` to the data value, removing the leading space from tokens like `' world'`.
- **Fix:** Changed parser to strip only the `data:` prefix and at most one separator space, preserving the payload exactly.
- **Files modified:** `tests/test_chat_stream.py`
- **Commit:** `78c9c54` (part of task 2 commit)

**2. [Rule 2 - Missing Critical Functionality] Temp-file SQLite for cross-thread test isolation**
- **Found during:** Task 2 tests
- **Issue:** `sqlite:///:memory:` databases are connection-scoped; sse_starlette's ASGI runner opens new DB connections from worker threads, seeing a fresh empty DB — all session store calls failed with "no such table: turn".
- **Fix:** Replaced in-memory engine fixture with temp-file engine fixture (`tempfile.NamedTemporaryFile`).
- **Files modified:** `tests/test_chat_stream.py`
- **Commit:** `78c9c54` (part of task 2 commit)

---

## Known Stubs

None. All functions wired to real OpenAI streaming API and real SQLite session store.

---

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: info_disclosure | `src/routes/chat.py` | T-05-02 mitigated: mid-stream LLMProviderError emits generic "LLM provider unavailable" — no key/stack trace |
| threat_flag: injection | `src/routes/chat.py` | T-05-03 mitigated: citations built from real Citation models, JSON-serialized with model_dump() |

No new unmitigated threat surfaces introduced.

---

## Self-Check: PASSED

Files confirmed on disk:
- trading-chatbot/backend/src/llm_client.py: FOUND (stream_complete present)
- trading-chatbot/backend/src/routes/chat.py: FOUND (/chat/stream present)
- trading-chatbot/backend/tests/test_chat_stream.py: FOUND (13 tests)

Nested repo commits confirmed:
- 6a63e98: feat(01-05): add stream_complete generator to llm_client
- 78c9c54: feat(01-05): POST /chat/stream SSE endpoint + 13 streaming tests

pytest: 46 passed, 5 skipped (live-index tests skip without PINECONE_READ_KEY) — suite is green.

---

*Phase: 01-chatbot-mvp*
*Completed: 2026-06-08*
