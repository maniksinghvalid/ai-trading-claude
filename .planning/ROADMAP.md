# Roadmap: Trading Chatbot

## Overview

Ship a cited, memory-grounded trading chatbot in two phases. **Phase 1 (Chatbot MVP)** delivers
a working personal chatbot end-to-end — Python backend, Pinecone retrieval, RAG chat, multi-turn
persistence, SSE streaming, and a Next.js streaming UI. **Phase 2 (Production Polish)** adds the
hardening that makes it multi-user and deployable — automatic ticker/intent extraction, live
market data, magic-link auth, Postgres, rate limiting, frontend polish, and containerized
deployment. Every slice has a runnable gate. Derived from `plan/trading-chatbot.md`.

## Phases

**Phase Numbering:**

- Integer phases (1, 2): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Chatbot MVP** - Backend + Pinecone RAG + streaming + Next.js chat, end-to-end (completed 2026-06-08)
- [ ] **Phase 2: Production Polish** - Ticker/intent, live quotes, auth, Postgres, rate limits, deploy

## Phase Details

### Phase 1: Chatbot MVP

**Goal**: As a trader, I want to chat about my holdings and ask follow-up questions that remember the prior ticker, so that I can trust the answer and verify it against the cited source reports.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: BOOT-01, BOOT-02, RAG-01, RAG-02, CHAT-01, CONV-01, STREAM-01, UI-01, VERIFY-NODATA
**Success Criteria** (what must be TRUE):

  1. In the browser, a question about a ticker streams an assistant response token-by-token with a Sources list rendered under the bubble.
  2. A follow-up message in the same session resolves the prior ticker without the user restating it.
  3. `/readyz` returns 200 with a real Pinecone `vector_count` and backend `pytest` passes.
  4. Every chat answer ends with the educational/not-financial-advice disclaimer; an unknown ticker yields a graceful no-data response, not a hallucinated citation.

**Plans**: 6 plans + 1 gap closure

Plans:

- [x] 01-01: Repo bootstrap + schema-contract doc + live-index smoke (slice 0)
- [x] 01-02: Backend skeleton + Pinecone client + health/ready (slice 1)
- [x] 01-03: OpenAI client + non-streaming RAG chat endpoint (slice 2)
- [x] 01-04: Conversation persistence + multi-turn coreference (slice 3)
- [x] 01-05: SSE streaming endpoint (slice 4)
- [x] 01-06: Next.js streaming chat frontend (slice 5)
- [x] 01-07: Gap closure — fix CRLF SSE parser (Gap 1, blocker) + wire ticker input through streamChat (Gap 2, major) + browser E2E re-verify (completed 2026-06-08)

### Phase 2: Production Polish

**Goal**: Make the chatbot multi-user and deployable — automatic ticker/intent resolution, live
market data, auth + isolation, Postgres, rate limiting, polished UI, and a public deployment.
**Depends on**: Phase 1
**Requirements**: TICK-01, QUOTE-01, AUTH-01, DB-01, RATE-01, POLISH-01, DEPLOY-01, VERIFY-SCHEMA
**Success Criteria** (what must be TRUE):

  1. A message with no explicit ticker auto-resolves to the right symbol, and "what's X trading at?" returns a live quote card while outlook questions return cited memory only.
  2. Unauthenticated `/chat` returns 401 and a logged-in user sees only their own sessions.
  3. Spamming past the per-user daily budget returns 429 with a `retry-after` header.
  4. The full stack is reachable at a public URL and chat works end-to-end through the deployed services; the schema-regression test passes in CI.

**Plans**: 7 plans
Plans:
**Wave 1**

- [ ] 02-01: Ticker extraction + intent classification + coreference (slice 6)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 02-02: Live market-data quote layer (slice 7)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 02-03: Magic-link auth + per-user session isolation (slice 8)

**Wave 4** *(blocked on Wave 3 completion)*

- [ ] 02-04: Postgres migration (slice 9)

**Wave 5** *(blocked on Wave 4 completion)*

- [ ] 02-05: Rate limiting + cost tracking (slice 10)
- [ ] 02-06: Frontend polish — sessions, citations, chips (slice 11)

**Wave 6** *(blocked on Wave 5 completion)*

- [ ] 02-07: Containerized deployment (slice 12)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Chatbot MVP | 7/7 | Complete   | 2026-06-08 |
| 2. Production Polish | 0/7 | Not started | - |
