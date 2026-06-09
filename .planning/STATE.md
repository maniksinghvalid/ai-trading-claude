---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-06-09T15:31:55.752Z"
last_activity: 2026-06-09 -- 02-04 completed (Postgres migration + retrieved_chunk_ids audit column)
progress:
  total_phases: 2
  completed_phases: 1
  total_plans: 14
  completed_plans: 11
  percent: 79
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Every factual claim is grounded in a real, cited stored report.
**Current focus:** Phase 02 — production-polish

## Current Position

Phase: 02 (production-polish) — EXECUTING
Plan: 5 of 7
Status: Ready to execute
Last activity: 2026-06-09 -- 02-04 completed (Postgres migration + retrieved_chunk_ids audit column)

Progress: [████████░░] 79% (milestone, 11/14 plans) · 02-04 complete (4/7 Phase 2 plans)

## Accumulated Context

### Decisions

- The chatbot is a SEPARATE repo (`trading-chatbot/`); these `.planning/` artifacts are a
  conversion staging area inside `ai-trading-claude`.

- Source of truth for slice detail is `plan/trading-chatbot.md`; CONTEXT.md per phase distills
  the locked decisions and points the planner back at it.

- Upstream Pinecone schema contract is read-only and versioned by the producer
  (`ai-trading-claude/scripts/trade_schemas.py` → README "Consumer Integration").

- [Phase ?]: trading-chatbot/ initialized as a nested git repo; outer repo does not git-track it (no gitlink)
- [Phase ?]: smoke_index.py exits 0 on missing PINECONE_READ_KEY — safe to run in CI without credentials
- [Phase ?]: openai_model defaults to gpt-4o (current flagship)
- [Phase ?]: retrieve() dual-filter: server-side Pinecone filter as best-effort + always post-filter returned matches (retrieval gotcha mitigation)
- [Phase ?]: live_index pytest marker + conftest auto-skip pattern for credential-gated Pinecone tests
- [02-04]: Column(JSON) via sa_column override makes list[str] work on both SQLite and Postgres without type-casting
- [02-04]: docker-compose.yml omits version: attribute (Compose v2 considers it obsolete)
- [02-04]: postgres marker auto-skip mirrors live_index pattern for Postgres integration tests
- [01-03]: No-data path short-circuits before LLM call — zero chunks yields fixed graceful message, no OpenAI tokens spent
- [01-03]: Pinecone retrieval failure degrades to no-data (graceful) rather than 503
- [01-03]: Citations built from real chunk metadata only — partial metadata records silently dropped
- [01-04]: Coreference via stored ticker_scope — req.ticker=None inherits most recent non-null ticker_scope from history, no LLM call needed (Phase 2 slice 6 adds full extraction)
- [01-04]: No-data path also persists both turns so follow-up turns have complete prior context
- [02-01]: 3-tier ticker resolution: explicit req.ticker > first extracted > coreference ticker_scope
- [02-01]: LLM fallback in ticker_extractor fires only when regex yields zero candidates (cost bound)
- [02-01]: classify_intent degrades to factual + regex tickers on any LLM failure
- [02-01]: intent result stored in local var for slice 7; no live-quote logic added yet
- [02-01]: autouse pytest fixture pattern for offline stubs avoids modifying every existing test
- [02-02]: yfinance 1.4.1 pinned via uv add; _fetch_raw() factored as monkeypatch target so all tests run offline
- [02-02]: intent-gated quote — factual + price-keyword (now/current/today/price/trading at/quote) + resolved ticker = fetch live quote; all other intents skip
- [02-02]: QuoteUnavailableError always degrades gracefully; chat never 503 due to quote provider failure
- [02-02]: event: quote emitted after citations and before first token in SSE stream (additive to locked order; no reordering)
- [01-05]: Temp-file SQLite in streaming tests — SQLite :memory: is connection-scoped; sse_starlette ASGI runner opens new connections in worker threads that see empty DBs
- [01-05]: Sync generator for stream_complete — OpenAI streaming SDK is synchronous; consumed inline in async event generator
- [Phase ?]: Native fetch + ReadableStream for SSE (POST /chat/stream — EventSource is GET-only)
- [Phase ?]: ReactMarkdown without rehype-raw: XSS defense T-06-01 for LLM output in chat UI
- [Phase ?]: sessionId in React state: Phase 1 single-user MVP; cross-reload persistence deferred to Phase 2

### Constraints

- Consumer-only: never writes to the `trade-reports` index in v1.
- Prefer ID-prefix retrieval over metadata `$eq`/`$in` filters (unreliable on this index).

## Notes

This project was bootstrapped by converting an existing detailed plan rather than via
`/gsd-new-project`. The standard codebase-grounding gates (pattern-mapper, intel surface,
schema-push, UI-safety) are not meaningful here because the target is a new repo that does not
yet exist in this tree — planning is grounded against `plan/trading-chatbot.md` instead.

## Performance Metrics

| Phase | Plan | Duration | Notes |
|-------|------|----------|-------|
| Phase 01-chatbot-mvp P01 | 202 | 3 tasks | 10 files |
| Phase 01-chatbot-mvp P02 | 25min | 3 tasks | 12 files |
| Phase 01-chatbot-mvp P03 | ~3min | 3 tasks | 6 files |
| Phase 01-chatbot-mvp P04 | ~15min | 2 tasks | 5 files |
| Phase 01-chatbot-mvp P05 | 20min | 2 tasks | 3 files |
| Phase 01-chatbot-mvp P06 | 20min | - tasks | - files |
| Phase 02-production-polish P01 | ~15min | 3 tasks | 8 files |
| Phase 02-production-polish P02 | 6min | 3 tasks | 10 files |
| Phase 02-production-polish P03 | 16min | 3 tasks | 13 files |
| Phase 02-production-polish P04 | ~15min | 3 tasks | 6 files |
