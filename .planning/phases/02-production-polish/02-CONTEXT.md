# Phase 2: Production Polish - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Source:** Converted from `plan/trading-chatbot.md` (slices 6–12)

<domain>
## Phase Boundary

Phase 2 hardens the MVP into a multi-user, deployable product. It builds on the Phase 1 backend
+ frontend and adds: automatic ticker extraction + intent classification, a live market-data
quote layer, magic-link auth + per-user isolation, a Postgres migration, rate limiting + cost
tracking, frontend polish, and containerized deployment.

**In scope (slices 6–12):** `ticker_extractor.py`, `intent_classifier.py`, `market_data.py` +
`/quote/{ticker}`, `auth.py` + `/auth` + JWT middleware, Postgres via docker-compose,
`rate_limiter.py` + `/admin/budgets`, polished frontend components (SessionList, CitationCard,
QuoteCard, TickerChip, StreamingMarkdown), Dockerfiles + deployment docs.

**Depends on Phase 1** being green (backend `/chat`, `/chat/stream`, session store, Next.js UI).
</domain>

<decisions>
## Implementation Decisions

### Ticker extraction + intent (slice 6, locked)
- Ticker extractor: rule-based first pass (regex `\$?[A-Z]{1,5}(\.[A-Z])?`) validated against a
  known-tickers list (from holdings + cache), LLM fallback for ambiguous mentions ("Apple" →
  AAPL). Guard false positives like "I" (Intelsat) via the holdings/known list.
- Intent classifier: small Anthropic call, fixed schema →
  `{intent: factual|trajectory|comparison|action|chitchat, tickers:[...]}`.
- Coreference: if a new message has no ticker but the last assistant message did, inherit the
  ticker scope from `session_store`.
- `/chat` calls the extractor before retrieval.

### Live market data (slice 7, locked)
- `market_data.py`: thin yfinance wrapper, `quote(ticker) -> {price, day_change_pct, volume,
  timestamp, source:"yfinance"}`, in-memory dict cache with ~15-min TTL. Timestamp every quote
  (yfinance is ~15 min delayed — document the delay in help text).
- Intent classifier decides when to fetch a live quote (keywords: now/current/today/price/
  "trading at"). Quote rendered in a separate `QuoteCard`, distinct from cited memory chunks.
- `prompts.py` injects the live quote inset when relevant (the `live_quote` arg from Phase 1).

### Auth (slice 8, locked)
- Magic-link email via Resend or Postmark; one-time signed URL → backend issues a 24h JWT on
  click. `/chat` and `/sessions` require `Authorization: Bearer <jwt>`. `session_store` gains a
  `user_id` column; `list_sessions()` filters by current user.

### Postgres migration (slice 9, locked)
- Add Postgres service to docker-compose; `database_url=postgresql+psycopg://...`. SQLModel
  table defs migrate cleanly (no new code). Add `retrieved_chunk_ids: list[str]` audit column
  on `Turn`.

### Rate limiting + cost (slice 10, locked)
- Per-user daily budget (max N chat requests, max M Anthropic input tokens) as a `UserBudget`
  SQLModel table with midnight-UTC reset; Pinecone read budget tracked similarly. 429 +
  `retry-after` when exceeded. `/admin/budgets` shows usage.

### Frontend polish (slice 11, locked)
- Sidebar lists prior sessions (`GET /sessions`); clicking loads history (`GET /sessions/{id}`).
  Citation cards expand to chunk text; ticker chips highlight detected tickers; incremental
  markdown rendering (debounced parse) for smooth streaming.

### Deployment (slice 12, locked)
- Backend Dockerfile: multi-stage uv build, final runs `uvicorn`. Frontend Dockerfile: standard
  Next.js production build. Secrets in the deploy platform (Fly.io/Railway backend, Vercel
  frontend), not in repo. Backend HTTPS-only; frontend env points at backend URL.
  `docs/deployment.md` documents one-command deploy per service.

### Claude's Discretion
- Email provider choice (Resend vs Postmark) and JWT library.
- Exact rate-limit thresholds (informed by the cost table: ~50 turns/day single-user).
- Deploy target specifics (Fly.io vs Railway) and CI wiring for the schema-regression test.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source plan (authoritative slice detail)
- `plan/trading-chatbot.md` — slices 6–12, plus the Risks, Cost estimate, and Verification
  (cross-slice) sections. Single source of truth for any detail not captured above.

### Phase 1 artifacts (build-on, do not duplicate)
- `.planning/phases/01-chatbot-mvp/01-CONTEXT.md` — locked Phase 1 decisions and the upstream
  schema contract Phase 2 continues to consume.

### Upstream schema contract (read-only)
- `README.md` → "Consumer Integration" and `scripts/trade_schemas.py` (in this repo) — the
  producer contract; the schema-regression test (VERIFY-SCHEMA) asserts it on every commit.
</canonical_refs>

<specifics>
## Specific Ideas

- Per-slice runnable gates (use as task acceptance criteria):
  - Slice 6: "how is apple doing" → AAPL; "and microsoft?" → MSFT while keeping AAPL in scope.
  - Slice 7: "what's AAPL trading at?" → quote card; "what's the outlook for AAPL?" → cited
    memory, no quote card.
  - Slice 8: unauthenticated `/chat` → 401; logged-in user sees only their sessions.
  - Slice 9: restart with Postgres URL → existing chat flow unchanged; sessions persisted.
  - Slice 10: spam 100 requests → 429 after the limit; budget resets midnight UTC.
  - Slice 11: refresh → sessions in sidebar → click → full history restored.
  - Slice 12: public URL responds; chat works end-to-end through the deployed stack.
- Quality gates (from the source plan's Verification D): citations on every claim; no-data
  graceful state; first token < 2s; session continuity; coreference; cost ceiling; auth
  isolation; schema-regression in CI.
</specifics>

<deferred>
## Deferred Ideas

- Real-time (<1s) market data via a paid feed (Polygon/IEX) — only if usage warrants.
- `report_type=CHAT` ingest path to enrich the index from chatbot insights — explicit future
  opt-in, kept out to avoid polluting the reports namespace.
</deferred>

---

*Phase: 02-production-polish*
*Context gathered: 2026-06-08 via conversion of plan/trading-chatbot.md*
