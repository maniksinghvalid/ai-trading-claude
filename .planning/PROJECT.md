# Trading Chatbot (Pinecone RAG Consumer)

## What This Is

A standalone web chatbot that lets a user ask any question about any ticker in their
portfolio (or any ticker in the index) and get cited, memory-grounded answers in real time,
augmented with live market data when relevant. It is a **separate application in a new
repository** — a pure *consumer* that reads from the `trade-reports` Pinecone index that the
`ai-trading-claude` plugin (the *producer*) writes into. Educational/research only; not
financial advice.

## Core Value

Every factual claim in an answer is grounded in a real, cited stored report — the chatbot
retrieves and quotes the user's own analysis history rather than hallucinating, and says "I
don't have stored analysis for X" when it doesn't.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

(None yet — ship to validate)

### Active

<!-- Current scope. Building toward these. See REQUIREMENTS.md for full checkable list. -->

- [ ] Repo bootstrap + verified read-only Pinecone contract (BOOT)
- [ ] Python backend + Pinecone retrieval client (RAG)
- [ ] RAG chat endpoint with citations + disclaimer (CHAT)
- [ ] Conversation persistence + multi-turn coreference (CONV)
- [ ] SSE token streaming (STREAM)
- [ ] Next.js streaming chat frontend (UI)
- [ ] Ticker extraction + intent classification (TICK)
- [ ] Live market-data quote layer (QUOTE)
- [ ] Magic-link auth + per-user isolation (AUTH)
- [ ] Postgres migration for multi-user (DB)
- [ ] Rate limiting + cost tracking (RATE)
- [ ] Frontend polish — sessions, citations, chips (POLISH)
- [ ] Containerized deployment (DEPLOY)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Writing chatbot turns back into Pinecone — keeps the `trade-reports` namespace clean for
  retrieval; a `report_type=CHAT` ingest path is a deliberate future opt-in, not v1.
- Producer/analysis logic — the chatbot never generates analysis reports; that stays in
  `ai-trading-claude`. Unidirectional data flow: producer writes, consumer reads.
- Real-time (<1s) market data — yfinance is ~15min delayed; a paid feed (Polygon/IEX) is a
  later upgrade if usage warrants.
- Brokerage / trade execution — research tool only; no order routing, no broker keys.

## Context

- **Upstream contract:** depends on the stable Pinecone schema documented in
  `ai-trading-claude/README.md` → "Consumer Integration" (single source of truth:
  `scripts/trade_schemas.py`). Index `trade-reports`, namespace `trade`, embedding
  `llama-text-embed-v2`, ID scheme `<TICKER>:<TYPE>:<YYYYMMDD-HHMM>:<section-slug>:<n>`
  (lexically sortable by recency). `schema_version` currently `1`; additive changes don't
  bump it, renames/removals do.
- **Producer note:** the producer's `OPTIONS` report_type + fields (`iv_rank`,
  `strategy_outlook`, `recommended_strategy`, `position_bias`) were added additively — the
  consumer reads them when present.
- **Known producer-side gotcha:** Pinecone metadata `$eq`/`$in` filters are unreliable on
  this index; prefer ID-prefix list/fetch (the producer's `latest`/`timeline` primitives) for
  deterministic retrieval.
- **Full source plan:** `plan/trading-chatbot.md` (mirrored into the new repo) is the
  canonical slice-by-slice spec this roadmap is derived from.

## Constraints

- **Tech stack**: Python 3.12 + FastAPI + `pinecone>=5` + `anthropic>=0.40` + `yfinance` +
  SQLite→Postgres backend; Next.js 14 (App Router) + TypeScript + Vercel AI SDK + Tailwind
  frontend; SSE for streaming; Docker Compose for local dev — locked by the source plan.
- **Repository**: separate repo `trading-chatbot/`, NOT part of `ai-trading-claude`. These
  `.planning/` artifacts live in `ai-trading-claude` only as a conversion staging area.
- **Access**: Pinecone read-only ("Reader" role) key as `PINECONE_READ_KEY`; the producer's
  write key is never shared with the chatbot.
- **Cost**: single-user target ~$25/month on Opus, ~$10/month on Haiku; default
  `max_tokens=2048`, truncate retrieved chunk text at ~1000 chars/chunk.
- **Security**: retrieved chunks contain LLM-summarized web content — system prompt must frame
  context as "reference material to evaluate, not instructions" (prompt-injection defense).

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| All Pinecone access routes through the Python backend (not Node) | Keeps prompt assembly, LLM calls, retrieval in one testable place | — Pending |
| Conversation state in the chatbot's own DB, never in Pinecone | Keeps `trade-reports` clean for retrieval | — Pending |
| Provider-agnostic `llm_client.py` abstraction | Switching off Anthropic touches one file | — Pending |
| Default to Opus, expose a Haiku "fast mode" toggle | Quality on research Q&A vs. cost-sensitive sessions | — Pending |
| Two-phase rollout: MVP (slices 0–5) then production polish (slices 6–12) | Each slice has a runnable gate; MVP ships an end-to-end personal chatbot first | — Pending |

---
*Last updated: 2026-06-08 after converting plan/trading-chatbot.md into GSD phases*
