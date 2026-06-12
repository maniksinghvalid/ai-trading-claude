---
phase: 02-production-polish
plan: 08
subsystem: backend
tags: [bug-fix, coreference, history-windowing, tdd, gap-closure]
dependency_graph:
  requires: [02-01, 02-02, 02-04]
  provides: [correct-most-recent-N-history-window, coreference-gap-closure, nodata-affirmative-gap-closure]
  affects: [session_store.history, routes.chat.post_chat, routes.chat._event_generator]
tech_stack:
  added: []
  patterns: [DESC-LIMIT-reversed-to-ASC, offered-ticker-pin, TDD-red-green]
key_files:
  created: []
  modified:
    - trading-chatbot/backend/src/session_store.py
    - trading-chatbot/backend/src/routes/chat.py
    - trading-chatbot/backend/tests/test_session_store.py
    - trading-chatbot/backend/tests/test_chat_endpoint.py
decisions:
  - "history() uses ORDER BY turn_index DESC LIMIT N + reversed to ASC — ensures tail of conversation is the context window"
  - "_offered_ticker() helper pins the offered-ticker scope in the affirmative branch (defense-in-depth for QUOTE-01)"
metrics:
  duration: ~5 minutes
  completed: 2026-06-11
  tasks_completed: 2
  files_modified: 4
requirements: [TICK-01, QUOTE-01]
---

# Phase 02 Plan 08: History Windowing + Coreference Gap Closure Summary

**One-liner:** Fixed `history()` to window the most-recent N turns (DESC LIMIT + reversed to ASC) and hardened the no-data affirmative branch with `_offered_ticker()` to pin the just-offered ticker — closes UAT test 3 (coreference) and test 5 (no-data "yes").

## What Was Built

### Task 1: history() most-recent-N windowing (TDD)

**Root cause:** `session_store.history()` used `ORDER BY turn_index ASC LIMIT N` — returning the OLDEST N turns. Once a conversation exceeded `_HISTORY_LIMIT=10`, recently-switched tickers and no-data offers fell outside the window. `reversed(prior_turns)` then saw only old turns, resolving stale tickers.

**Fix:** Changed the SELECT to `ORDER BY turn_index DESC LIMIT N`, then `reversed()` the result list back to ASC before returning. Callers get the tail of the conversation in display/LLM order — no API change.

TDD gate:
- RED: Updated `test_history_respects_limit` to assert turn_index 7-9 (not 0-2). Added `test_history_returns_most_recent_when_over_limit` and `test_coreference_newest_scope_across_window` (MARA early + CLOV recent = resolves CLOV). All 3 failed.
- GREEN: Applied `order_by(Turn.turn_index.desc()) + reversed()` in `history()`. All 3 now pass; 21 session_store tests pass.

### Task 2: No-data affirmative hardening + chat regression tests (TDD)

**Behavior after Task 1:** With history() windowing the most-recent turns, both UAT gaps already closed via the existing logic — coreference and `_prev_offered_live_data` now see the recent CLOV and AAPL offer turns respectively.

**Additional hardening:** Added `_offered_ticker(prior_turns) -> str | None` that reads the `ticker_scope` of the most recent assistant "live market data" offer turn. In both `post_chat` and `_event_generator`, the affirmative branch now uses `_offered_ticker(prior_turns) or ticker_upper` — ensuring the offered ticker is used even if generic coreference would resolve a different stale ticker (defense-in-depth for QUOTE-01).

Regression tests added to `test_chat_endpoint.py`:
- `test_coreference_resolves_most_recent_ticker`: HTTP-drives MARA → CLOV → bare "stock price", captures `retrieve()` kwargs, asserts ticker="CLOV"
- `test_nodata_affirmative_fetches_offered_ticker`: HTTP-drives AAPL no-data offer → "yes", asserts `market_data.quote("AAPL")` called

TDD gate: Both tests passed on first run (root cause already fixed by Task 1 — expected per plan).

## Deviations from Plan

None — plan executed exactly as written. The plan anticipated that Task 1 would close both gaps and Task 2 would confirm with regression tests + add the `_offered_ticker` hardening.

## Verification

```
cd trading-chatbot/backend && uv run pytest     # 139 passed, 7 skipped
grep -n "turn_index.desc" trading-chatbot/backend/src/session_store.py  # shows line ~175
```

Full suite: **139 passed, 7 skipped** (all skips are expected: postgres integration, live pinecone, etc.)

## Commits (trading-chatbot/ inner repo, branch main)

| Hash    | Type | Description |
|---------|------|-------------|
| 746134a | test | add failing tests for history() most-recent-N windowing (RED) |
| 5e32877 | fix  | history() returns most-recent N turns (DESC LIMIT + reversed to ASC) (GREEN) |
| 1a1c645 | fix  | harden no-data affirmative path + add coreference/quote regression tests |

## Threat Surface Scan

No new network endpoints, auth paths, or trust boundaries introduced. The ORM-only query change in `history()` is covered by T-08-01 (ownership filter preserved). The `_offered_ticker` helper reads from the same user-scoped windowed turns — no cross-user leakage (T-08-02).

## Self-Check: PASSED

- `trading-chatbot/backend/src/session_store.py` — modified, verified `turn_index.desc` present
- `trading-chatbot/backend/src/routes/chat.py` — modified, `_offered_ticker` added
- `trading-chatbot/backend/tests/test_session_store.py` — 3 new/updated tests pass
- `trading-chatbot/backend/tests/test_chat_endpoint.py` — 2 new regression tests pass
- All 3 inner-repo commits exist on `trading-chatbot` branch main
- `uv run pytest`: 139 passed, 7 skipped
