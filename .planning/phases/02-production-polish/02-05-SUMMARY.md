---
phase: 02-production-polish
plan: 05
subsystem: backend/rate-limiting
tags: [rate-limiting, cost-tracking, sqlite, sqlmodel, fastapi, tdd]
dependency_graph:
  requires: [02-03, 02-04]
  provides: [RATE-01]
  affects: [trading-chatbot/backend/src/rate_limiter.py, trading-chatbot/backend/src/routes/admin.py, trading-chatbot/backend/src/routes/chat.py]
tech_stack:
  added: []
  patterns: [per-user daily budget, midnight-UTC reset, 429 + Retry-After, SQLModel reuse, TDD RED/GREEN]
key_files:
  created:
    - trading-chatbot/backend/src/rate_limiter.py
    - trading-chatbot/backend/src/routes/admin.py
    - trading-chatbot/backend/tests/test_rate_limiter.py
  modified:
    - trading-chatbot/backend/src/config.py
    - trading-chatbot/backend/src/routes/chat.py
    - trading-chatbot/backend/src/main.py
decisions:
  - "UserBudget stores usage_date as ISO date string (YYYY-MM-DD) — SQLite has no native date type; string comparison is sufficient for daily-boundary checks"
  - "engine re-exported from rate_limiter for consistent monkeypatching in tests (both ss.engine and rl.engine must be patched to same StaticPool instance)"
  - "Budget check in post_chat_stream is in the sync function body BEFORE EventSourceResponse — ensures 429 is a normal HTTP response, not an SSE event"
  - "daily_request_budget default=200 (~4x the 50 turns/day single-user estimate from cost table, multi-user headroom)"
metrics:
  duration: ~15min
  completed: "2026-06-09"
  tasks: 3
  files: 6
---

# Phase 2 Plan 05: Per-user Rate Limiting + Cost Tracking Summary

**One-liner:** Per-user daily budget (request + input-token caps) via a UserBudget SQLModel table with midnight-UTC reset, 429 + Retry-After enforcement on /chat and /chat/stream, and a /admin/budgets visibility endpoint behind an X-Admin-Token gate.

## Objective

Implement RATE-01: prevent a single user from spamming long-context queries and running up large OpenAI bills. Caps are per-user per day; the budget resets at midnight UTC.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED  | Failing tests for rate limiter | 945ece8 | tests/test_rate_limiter.py |
| 1 GREEN | UserBudget table + check_and_increment | 16033fc | rate_limiter.py, config.py, test_rate_limiter.py |
| 2 | Gate /chat + /chat/stream with 429 | 3f62584 | routes/chat.py |
| 3 | GET /admin/budgets endpoint | 1824d25 | routes/admin.py, main.py |

## Implementation Notes

### rate_limiter.py

- `UserBudget` SQLModel table: `user_id` (PK str), `usage_date` (str ISO), `request_count` (int), `input_token_count` (int). Reuses the shared engine from `session_store`.
- `check_and_increment(user_id, input_tokens=0)`: loads or creates row; resets counts when `usage_date != today_utc`; raises `BudgetExceeded` (before incrementing) when either cap exceeded; increments and commits on success.
- `BudgetExceeded(RuntimeError)`: carries `retry_after_seconds = _seconds_to_next_midnight(now)`.
- `_now()` helper: patchable by tests for deterministic clock assertions.
- `current_usage(user_id=None)`: returns list of all rows or single dict.

### config.py additions

| Field | Default | Rationale |
|-------|---------|-----------|
| `daily_request_budget` | 200 | ~4x single-user ceiling; set via DAILY_REQUEST_BUDGET |
| `daily_input_token_budget` | 2_000_000 | ~50 turns × 2k tokens × 10 users + headroom |
| `admin_token` | "change-me-in-production" | Set ADMIN_TOKEN in env before deploy |

### routes/chat.py

Both `post_chat` and `post_chat_stream` call `check_and_increment(user_id)` as the very first operation after auth. For `/chat/stream`, the check runs in the synchronous wrapper (not the async generator) so a 429 is a regular HTTP response with `Retry-After: <seconds>` header — the SSE stream is never opened.

### routes/admin.py

`GET /admin/budgets` checks `X-Admin-Token` header against `settings.admin_token`; returns 401 on mismatch. Supports optional `?user_id=` query param for per-user filtering.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion used date object vs. ISO string**
- **Found during:** Task 1 GREEN phase (test_midnight_utc_reset)
- **Issue:** Test asserted `row.usage_date == today` where `today` was a `date` object, but `UserBudget.usage_date` is stored as an ISO string (`"2026-06-09"`). SQLite has no native date type; string storage was the correct design choice.
- **Fix:** Changed test assertion to compare against `today_str = "2026-06-09"`.
- **Files modified:** tests/test_rate_limiter.py
- **Commit:** 16033fc (included in GREEN commit)

## TDD Gate Compliance

- RED gate: `test(02-05)` commit `945ece8` — failing tests confirmed (ModuleNotFoundError on import)
- GREEN gate: `feat(02-05)` commit `16033fc` — implementation passes all unit tests

## Verification

Full backend suite: `uv run pytest` → **135 passed, 7 skipped** (live-index, postgres, schema-contract — all credential-gated), 0 failed.

Slice 10 runnable gate: spam N requests → 429 after the limit (Retry-After numeric header); budget resets at midnight UTC (tested with patched clock); /admin/budgets returns usage.

## Known Stubs

None. All budget thresholds use production-reasonable defaults; no placeholder data flows to any UI surface.

## Threat Flags

No new network endpoints beyond the planned `/admin/budgets` surface. All threat mitigations implemented as specified:
- T-02-05-01: request + token caps enforced (BudgetExceeded → 429 + Retry-After)
- T-02-05-02: /admin/budgets behind X-Admin-Token check (401 on mismatch)
- T-02-05-03: user_id taken from JWT in get_current_user, never from request body

## Self-Check

Files exist:
- trading-chatbot/backend/src/rate_limiter.py: CREATED
- trading-chatbot/backend/src/routes/admin.py: CREATED
- trading-chatbot/backend/tests/test_rate_limiter.py: CREATED
- trading-chatbot/backend/src/config.py: MODIFIED
- trading-chatbot/backend/src/routes/chat.py: MODIFIED
- trading-chatbot/backend/src/main.py: MODIFIED

Commits in trading-chatbot repo: 945ece8, 16033fc, 3f62584, 1824d25

## Self-Check: PASSED
