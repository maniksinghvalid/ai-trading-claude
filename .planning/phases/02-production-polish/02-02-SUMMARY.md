---
phase: 02-production-polish
plan: 02
subsystem: market-data
tags: [yfinance, quote, caching, sse, intent-routing, tdd]
dependency_graph:
  requires: [02-01]
  provides: [market_data.quote, GET /quote/{ticker}, intent-gated-quote-injection]
  affects: [trading-chatbot/backend/src/routes/chat.py, trading-chatbot/backend/src/prompts.py]
tech_stack:
  added: [yfinance==1.4.1]
  patterns: [in-memory TTL cache, lazy import, SSE event extension, graceful degradation]
key_files:
  created:
    - trading-chatbot/backend/src/market_data.py
    - trading-chatbot/backend/src/routes/quote.py
    - trading-chatbot/backend/tests/test_market_data.py
  modified:
    - trading-chatbot/backend/src/routes/chat.py
    - trading-chatbot/backend/src/prompts.py
    - trading-chatbot/backend/src/main.py
    - trading-chatbot/backend/tests/test_chat_endpoint.py
    - trading-chatbot/backend/tests/test_chat_stream.py
    - trading-chatbot/backend/pyproject.toml
    - trading-chatbot/backend/uv.lock
decisions:
  - "yfinance 1.4.1 pinned via uv add (0.2.x was the plan spec but latest stable is 1.4.1 — uv resolved it)"
  - "_fetch_raw() factored as a private helper for monkeypatching so all tests run fully offline"
  - "_wants_live_quote() helper centralizes intent+keyword+ticker gating logic (DRY between /chat and /chat/stream)"
  - "QuoteUnavailableError always degrades to live_quote=None; chat never fails due to quote provider being down"
  - "event: quote emitted after citations, before first token — extends locked SSE order additively"
  - "price-keyword family: now/current/today/price/trading at/quote (frozenset)"
metrics:
  duration: "~6 min"
  completed: "2026-06-09T14:51:04Z"
  tasks_completed: 3
  files_created: 3
  files_modified: 7
---

# Phase 02 Plan 02: Live Market-Data Quote Layer Summary

**One-liner:** yfinance quote wrapper with 900s TTL cache, GET /quote/{ticker}, and intent-gated live-quote injection (factual + price-keyword) into /chat and /chat/stream SSE streams.

## What Was Built

### Task 0 (Checkpoint - Pre-approved)
Package legitimacy gate for `yfinance` was pre-approved by the user before execution. yfinance 1.4.1 installed via `uv add yfinance` and pinned in pyproject.toml + uv.lock.

### Task 1: market_data.py (TDD RED → GREEN)

**RED commit `806bd52`:** Wrote `tests/test_market_data.py` first — 12 tests covering:
- Five-key dict return shape with source=="yfinance" and ISO-8601 timestamp
- Cache hit (2 calls → 1 fetch), TTL expiry forcing re-fetch
- Uppercase normalization (aapl/AAPL share same cache entry)
- QuoteUnavailableError on provider failure with no key/stack leak
- GET /quote/{ticker} 200 + 503 paths

Tests failed as expected (ImportError — module not yet created).

**GREEN commit `36b711b`:** Implemented `market_data.py`:
- `_CACHE_TTL_SECONDS = 900`, `_cache: dict` module-level
- `_fetch_raw(ticker)` — lazy yfinance import, reads fast_info → price/day_change_pct/volume; raises RuntimeError on missing data
- `quote(ticker)` — uppercases ticker, checks cache (monotonic clock), calls `_fetch_raw` on miss, wraps all errors in `QuoteUnavailableError` (no stack/key leak — T-02-02-01)
- 9/12 unit tests pass (3 endpoint tests need routes/quote.py)

### Task 2: routes/quote.py + main.py registration

**Commit `c55f37e`:**
- `routes/quote.py`: `APIRouter(prefix="/quote")`, `GET /quote/{ticker}` → calls `market_data.quote(ticker.upper())`, catches `QuoteUnavailableError` → HTTP 503 with generic "quote provider unavailable" (no stack trace — T-02-02-01)
- `main.py`: `from src.routes.quote import router as quote_router` + `app.include_router(quote_router)` registered between chat and sessions routers
- All 12 test_market_data.py tests pass

### Task 3: Intent-gated quote injection

**Commit `45e4252`:**

`prompts.py`:
- `rag_user_prompt()` now renders a `## Live Quote` inset when `live_quote is not None`; includes price, day_change_pct, volume, timestamp, source, and a "~15 min delayed" disclaimer (T-02-02-03)

`routes/chat.py`:
- Added `_PRICE_KEYWORDS` frozenset: `{now, current, today, price, trading at, quote}`
- Added `_wants_live_quote(intent, message, ticker)` helper: returns True only when intent=="factual" AND price keyword matched AND ticker resolved
- `post_chat`: calls `market_data.quote(ticker_upper)` when `_wants_live_quote` → passes `live_quote=...` to `rag_user_prompt()`; QuoteUnavailableError caught, degrades to `live_quote=None`
- `post_chat_stream`: same gate; when quote fetched, emits `event: quote` (JSON) after `event: citations` and before first `event: token` — extends locked SSE order additively

Test additions:
- `test_chat_endpoint.py`: 4 new tests — price question calls quote(), prompt contains "Live Quote", outlook question does NOT call quote() (assert call_count==0), unavailable degrades gracefully to 200
- `test_chat_stream.py`: 4 new tests — quote event present for price question, payload has five keys, no quote event for outlook/trajectory intent, no quote event when QuoteUnavailableError raised

## Verification

```
cd trading-chatbot/backend && uv run pytest
97 passed, 6 skipped, 1 warning in 2.18s
```

6 skipped = live_index marker tests (require PINECONE_READ_KEY, intentional).

## Deviations from Plan

### yfinance version

The plan specified "pinned per the legitimacy-gate approval" (0.2.x implied). `uv add yfinance` resolved the current stable release 1.4.1 (API-compatible; same `yfinance.Ticker.fast_info` interface). This is the correct pinned version — no action needed.

No other deviations. Plan executed as written.

## Known Stubs

None — all quote functionality is fully wired. `rag_user_prompt` now renders the live quote when provided; `/chat` and `/chat/stream` both call `market_data.quote()` on price-intent requests.

## Threat Flags

None — all mitigations from the plan's threat model were implemented:
- T-02-02-01: QuoteUnavailableError wraps all provider errors; 503 returns generic detail
- T-02-02-02: 900s TTL cache in place; quote fetched only on price-intent
- T-02-02-03: timestamp + source label on every quote; delay noted in prompt inset

## Self-Check

Files created:
- trading-chatbot/backend/src/market_data.py
- trading-chatbot/backend/src/routes/quote.py
- trading-chatbot/backend/tests/test_market_data.py

Commits in nested repo (trading-chatbot):
- 806bd52 test(02-02): add failing tests (RED)
- 36b711b feat(02-02): implement market_data.quote (GREEN)
- c55f37e feat(02-02): add GET /quote endpoint + register router
- 45e4252 feat(02-02): intent-gated quote injection + prompts inset
