# Requirements: Trading Chatbot

**Defined:** 2026-06-08
**Core Value:** Every factual claim is grounded in a real, cited stored report.
**Source:** Derived from `plan/trading-chatbot.md` (slices 0–12).

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Bootstrap & Contract (Phase 1)

- [x] **BOOT-01**: New `trading-chatbot/` repo exists with `backend/`, `frontend/`, `docs/`,
  `plan/` skeleton and a committed `docs/schema-contract.md` carrying the read-only metadata
  field table.

- [x] **BOOT-02**: A live-index smoke (no app code) with the read-only key opens index
  `trade-reports`, runs `describe_index_stats()`, and confirms namespace `trade` exists
  without errors (vector count ≥ 0 acceptable).

### Retrieval Backend (Phase 1)

- [x] **RAG-01**: `pinecone_client` exposes `retrieve(text, ticker?, report_type?, k)`,
  `latest(ticker, report_type)`, and `timeline(ticker, limit)`, each returning normalized
  `{id, score, text, metadata}` chunks.

- [x] **RAG-02**: `/readyz` returns 200 with a real Pinecone `vector_count`; `/healthz`
  returns `{status:"ok"}`; backend `pytest` passes.

### Grounded Chat (Phase 1)

- [x] **CHAT-01**: `POST /chat` retrieves chunks, builds a RAG prompt, calls the LLM, and
  returns a coherent answer with a populated `citations[]` (when data exists) and a
  `session_id`; the answer ends with the educational/not-financial-advice disclaimer.

### Conversation State (Phase 1)

- [x] **CONV-01**: Two consecutive messages with the same `session_id` produce a response that
  references the prior turn's ticker without restating it; `GET /sessions` lists sessions and
  `GET /sessions/{id}` returns turn history.

### Streaming (Phase 1)

- [x] **STREAM-01**: `POST /chat/stream` emits SSE events `session` → `citations` → repeated
  `token` → `done`; tokens arrive incrementally over time, not all at once.

### Frontend MVP (Phase 1)

- [x] **UI-01**: The Next.js chat UI streams an assistant response token-by-token, renders a
  Sources list under the bubble from citations, and continues a session across messages.

## v2 Requirements

Production polish. Mapped to Phase 2.

### Ticker & Intent (Phase 2)

- [x] **TICK-01**: A message with no explicit ticker ("how is apple doing") resolves to AAPL;
  intent is classified (factual/trajectory/comparison/action/chitchat); a follow-up ("and
  microsoft?") resolves MSFT while keeping AAPL in scope (coreference).

### Live Market Data (Phase 2)

- [x] **QUOTE-01**: "what's AAPL trading at?" returns a live quote card (price, day change,
  volume, timestamp, source); "what's the outlook for AAPL?" returns cited memory with no
  quote card. Quotes are cached ~15 min and timestamped.

### Auth & Isolation (Phase 2)

- [x] **AUTH-01**: Magic-link email issues a 24h JWT on click; unauthenticated `/chat` returns
  401; a logged-in user sees only their own sessions (User A cannot access User B's sessions).

### Persistence Scale (Phase 2)

- [x] **DB-01**: Switching `database_url` to Postgres leaves the chat flow unchanged and
  sessions persisted across restart; a `retrieved_chunk_ids` audit column exists on `Turn`.

### Rate Limiting (Phase 2)

- [x] **RATE-01**: Exceeding the per-user daily budget returns 429 with a `retry-after`
  header; budget resets at midnight UTC; `/admin/budgets` shows current usage.

### Frontend Polish (Phase 2)

- [x] **POLISH-01**: A sidebar lists prior sessions; clicking one restores full history;
  citation cards expand to chunk text; ticker chips highlight detected tickers.

### Deployment (Phase 2)

- [x] **DEPLOY-01**: Backend and frontend run from Dockerfiles; secrets live in the deploy
  platform; a public URL serves the stack and chat works end-to-end through it.

## Cross-Cutting Verification

- [x] **VERIFY-SCHEMA**: A regression test retrieves one sample chunk and asserts all required
  metadata fields (`ticker`, `report_type`, `generated_at`, `generated_date`, `source_path`)
  are present; fails loudly if any is missing. Runs in CI on every commit.

- [x] **VERIFY-NODATA**: Querying a ticker absent from the index yields a graceful "I don't
  have stored analysis for XYZ" response — no hallucinated citations.
