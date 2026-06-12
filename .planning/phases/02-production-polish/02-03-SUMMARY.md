---
phase: 02-production-polish
plan: "03"
subsystem: auth
tags: [auth, jwt, magic-link, session-isolation, fastapi, nextjs]
dependency_graph:
  requires: [02-02]
  provides: [AUTH-01, user_id-data-model]
  affects: [02-04, 02-05, 02-06]
tech_stack:
  added: [pyjwt==2.13.0, resend==2.30.1]
  patterns: [FastAPI Depends, Header() dependency injection, StaticPool SQLite, HS256 JWT, magic-link flow]
key_files:
  created:
    - trading-chatbot/backend/src/auth.py
    - trading-chatbot/backend/src/routes/auth.py
    - trading-chatbot/frontend/app/login/page.tsx
    - trading-chatbot/frontend/app/auth/callback/page.tsx
  modified:
    - trading-chatbot/backend/src/config.py
    - trading-chatbot/backend/src/session_store.py
    - trading-chatbot/backend/src/routes/chat.py
    - trading-chatbot/backend/src/routes/sessions.py
    - trading-chatbot/backend/src/main.py
    - trading-chatbot/backend/pyproject.toml
    - trading-chatbot/backend/uv.lock
    - trading-chatbot/backend/tests/test_auth.py
    - trading-chatbot/backend/tests/test_chat_endpoint.py
    - trading-chatbot/backend/tests/test_chat_stream.py
    - trading-chatbot/backend/tests/test_session_store.py
    - trading-chatbot/frontend/lib/api.ts
decisions:
  - "PyJWT chosen for HS256 JWT issuance (established library, no heavy deps); Resend chosen for email provider (approved via package-legitimacy gate)"
  - "Magic-link tokens use 15-minute TTL via the same JWT library (sub=email, exp=now+900s); full JWT uses 24h TTL"
  - "get_current_user uses FastAPI Header() dependency injection so the Authorization header is read from the HTTP request, not a function argument"
  - "StaticPool replaces :memory: SQLite in auth+endpoint tests so ASGI worker threads share the same DB instance"
  - "User email address used as stable user_id (sub claim in JWT)"
  - "Resend from-address: noreply@updates.maniksingh.dev (user-configured; MVP domain)"
  - "_send_magic_link_email extracted as a standalone function so tests can monkeypatch it without importing resend"
  - "history(session_id, user_id=None) preserves Phase 1 behaviour (no filter) when called without user_id"
metrics:
  duration: "16 min"
  completed: "2026-06-09"
  tasks_completed: 3
  files_changed: 13
---

# Phase 2 Plan 03: Magic-Link Auth + Per-User Session Isolation Summary

Magic-link email auth + per-user session isolation (AUTH-01): a one-time signed 15-minute token issues a 24h HS256 JWT on click; `/chat`, `/chat/stream`, and `/sessions` require `Authorization: Bearer <jwt>`; `Turn` gains an indexed `user_id` column and `list_sessions` / `history` filter strictly by owner.

## What Was Built

### Checkpoint (pre-approved)
Package legitimacy gate was pre-approved by the user before execution began. Approved choices recorded:
- **JWT library:** PyJWT (pypi.org/project/PyJWT — jpadilla/pyjwt, widely maintained)
- **Email provider:** Resend (pypi.org/project/resend — official Resend Python SDK)

### Task 1: auth.py (TDD RED → GREEN)
- `issue_magic_link(email)` — mints a 15-min HS256 JWT URL (`magic_link_base_url?token=...`)
- `verify_magic_token(token)` — verifies and returns email, raises `AuthError` on expiry/tamper
- `issue_jwt(user_id)` — signs a 24h HS256 JWT with `sub=user_id`
- `decode_jwt(token)` — verifies signature + expiry, raises `AuthError` on failure
- `get_current_user(authorization: Optional[str] = Header(default=None))` — FastAPI dependency reading the Authorization header, stripping `Bearer `, calling `decode_jwt`, returning `sub`; raises `HTTPException(401)` on any failure
- `config.py` updated with: `jwt_secret`, `jwt_ttl_hours`, `email_provider_api_key`, `magic_link_base_url`, `frontend_base_url`
- All tests run offline; 10 unit tests passing

### Task 2: user_id column + user-scoped queries + /auth routes
- `Turn.user_id: str = Field(default="", index=True)` — indexed column on Turn
- `append_turn(..., user_id="")` — accepts and persists user_id
- `list_sessions(user_id)` — filters turns by `Turn.user_id == user_id` (cross-user isolation T-02-03-02)
- `history(session_id, user_id=None)` — ownership enforcement: non-owner returns `[]`
- `routes/auth.py`: `POST /auth/request-link` (sends via Resend, wrapped for 503 on failure), `GET /auth/callback` (verifies token, issues JWT, returns `{access_token, token_type}`)
- Auth router registered in `main.py`
- `test_session_store.py` updated to pass `user_id` to `list_sessions()`

### Task 3: Gate chat + sessions; frontend login + Bearer
- `POST /chat` and `POST /chat/stream`: `Depends(get_current_user)` added; `user_id` threaded into all `append_turn` calls
- `GET /sessions` and `GET /sessions/{session_id}`: `Depends(get_current_user)` added; user-scoped `list_sessions(user_id)` and `history(session_id, user_id=user_id)` calls
- `app/login/page.tsx`: email input → POST /auth/request-link → confirmation message (no link in response)
- `app/auth/callback/page.tsx`: handles both `?token=` (raw magic-link) and `?access_token=` (pre-minted JWT) flows; stores JWT in localStorage
- `lib/api.ts`: `getStoredToken()` reads from localStorage; `Authorization: Bearer <token>` added to `/chat/stream` fetch headers when token is present
- All pre-existing `test_chat_endpoint.py` and `test_chat_stream.py` tests updated with `auth_headers` fixture + Bearer headers

## Verification

```
cd trading-chatbot/backend && uv run pytest
118 passed, 6 skipped (Pinecone live-index, expected offline)

cd trading-chatbot/frontend && npm run build
✓ Compiled successfully (5 routes: /, /_not-found, /auth/callback, /login, + 404)
```

Slice 8 gate: unauthenticated `/chat` → 401; authenticated user sees only their sessions.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed FastAPI Header() injection for get_current_user**
- **Found during:** Task 3 GREEN verification
- **Issue:** `get_current_user(authorization: Optional[str] = None)` was not wired to the HTTP Authorization header — FastAPI would not auto-inject a plain parameter as a header. The dependency returned 401 even with a valid Bearer token.
- **Fix:** Changed to `authorization: Optional[str] = Header(default=None)` so FastAPI's dependency injection reads from the HTTP request headers.
- **Files modified:** `backend/src/auth.py`
- **Commit:** f058dea

**2. [Rule 2 - Missing critical] Updated pre-existing endpoint tests to include Bearer token**
- **Found during:** Task 3 full test run
- **Issue:** 18 tests in `test_chat_endpoint.py` + `test_chat_stream.py` called `/chat` and `/chat/stream` without Authorization headers — all returned 401 after auth gating was added.
- **Fix:** Added `auth_headers` fixture (issues a test JWT) and added `headers=auth_headers` to all HTTP calls. Also added `in_memory_db` (StaticPool) fixture to `test_chat_endpoint.py` to isolate tests.
- **Files modified:** `backend/tests/test_chat_endpoint.py`, `backend/tests/test_chat_stream.py`
- **Commit:** f058dea

**3. [Rule 2 - Missing critical] Updated test_session_store.py for new list_sessions(user_id) signature**
- **Found during:** Task 2 verification
- **Issue:** All `list_sessions()` calls in pre-existing tests now require `user_id` argument; tests failed with `TypeError`.
- **Fix:** Updated 4 test functions to pass `user_id="test@example.com"` and match turns using the same user_id in `append_turn` calls.
- **Files modified:** `backend/tests/test_session_store.py`
- **Commit:** a559998

**4. [Rule 2 - Missing critical] StaticPool for in-memory SQLite in auth endpoint tests**
- **Found during:** Task 2/3 auth endpoint test debugging
- **Issue:** SQLite `:memory:` is connection-scoped — TestClient's ASGI worker threads open new connections that see an empty DB, causing `no such table: turn` errors in integration tests.
- **Fix:** Changed `in_memory_db` fixture in `test_auth.py` to use `StaticPool` so all threads share the same connection and DB instance. Same pattern was already used in streaming tests (temp file); StaticPool is cleaner for non-stream tests.
- **Files modified:** `backend/tests/test_auth.py`
- **Commit:** f058dea

## Known Stubs

None. All auth flows are wired:
- Resend email send is real code (monkeypatched only in tests via `_send_magic_link_email`)
- JWT round-trips are real (PyJWT)
- Frontend login page POSTs to the real backend endpoint
- Bearer token is read from localStorage (real implementation)

## Threat Flags

No new security surface introduced beyond what the plan's threat model already covers (T-02-03-01 through T-02-03-SC). All planned mitigations implemented:
- T-02-03-01 (JWT forgery): HS256 + sig verification in decode_jwt
- T-02-03-02 (IDOR): history/list_sessions filter by user_id from token, not request body
- T-02-03-03 (info disclosure): generic 503 on provider failure; no key/stack in response
- T-02-03-04 (magic-link replay): 15-min TTL + exp enforced in verify_magic_token

## Commits (inner trading-chatbot repo)

| Hash | Message |
|------|---------|
| c1d601c | test(02-03): add failing tests for magic-link auth + JWT + user-scoped sessions (RED) |
| 0cc94e3 | feat(02-03): auth.py magic-link + JWT + current-user dependency (GREEN) |
| a559998 | feat(02-03): user_id column + user-scoped sessions + /auth routes (Task 2) |
| f058dea | feat(02-03): gate /chat + /sessions with get_current_user; frontend login + Bearer (Task 3) |

## Self-Check: PASSED

- [x] trading-chatbot/backend/src/auth.py exists
- [x] trading-chatbot/backend/src/routes/auth.py exists
- [x] trading-chatbot/frontend/app/login/page.tsx exists
- [x] trading-chatbot/frontend/app/auth/callback/page.tsx exists
- [x] All 4 commits present in inner repo (git -C trading-chatbot log --oneline)
- [x] `uv run pytest` → 118 passed, 6 skipped
- [x] `npm run build` → success (5 routes compiled)
- [x] .env NOT committed
