# Phase 1: Chatbot MVP - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning
**Source:** Converted from `plan/trading-chatbot.md` (slices 0–5)

<domain>
## Phase Boundary

Phase 1 delivers a working **personal** chatbot end-to-end in the new `trading-chatbot/` repo:
Python/FastAPI backend → Pinecone read-only retrieval → OpenAI RAG → SQLite conversation
store → SSE streaming → Next.js streaming chat UI. It is single-user (no auth), uses the
`ticker` passed explicitly by the caller (no auto-extraction yet — that is Phase 2), and reads
from the live `trade-reports` index produced by `ai-trading-claude`.

**In scope (slices 0–5):** repo bootstrap + schema-contract doc, Pinecone client
(retrieve/latest/timeline), health/ready endpoints, non-streaming RAG `/chat`, conversation
persistence + multi-turn, SSE `/chat/stream`, Next.js MVP frontend.

**Out of scope (deferred to Phase 2):** automatic ticker/intent extraction, live market-data
quotes, auth/multi-user, Postgres, rate limiting, frontend polish (sidebar/cards/chips),
deployment.
</domain>

<decisions>
## Implementation Decisions

### Repository & Layout (locked)
- Separate repo `trading-chatbot/` with `backend/`, `frontend/`, `docs/`, `plan/`. Backend is
  the ONLY component that talks to Pinecone; frontend talks only to the backend.
- Backend layout per the source plan: `src/{main,config,pinecone_client,llm_client,prompts,
  schemas}.py` + `src/routes/{health,chat,sessions}.py` + `tests/`.

### Backend stack (locked)
- Python 3.12, uv-managed venv. Deps: `fastapi>=0.115`, `uvicorn[standard]>=0.32`,
  `pinecone>=5`, `openai>=1.0`, `pydantic>=2.9`, `pydantic-settings>=2.6`,
  `sqlmodel>=0.0.22`, `psycopg[binary]>=3.2`, `sse-starlette>=2.1`, `httpx>=0.27`. Dev:
  `pytest>=8`, `pytest-asyncio>=0.24`, `respx>=0.21`.
  (`psycopg[binary]>=3.2` is the Postgres driver — present in the stack for the Phase 2
  Postgres migration; Phase 1 still runs on SQLite per the conversation-store decision below.)
- `config.py`: Pydantic `Settings` with `pinecone_read_key`, `pinecone_index="trade-reports"`,
  `pinecone_namespace="trade"`, `openai_api_key`, `openai_model` (default a current
  OpenAI model — verify the exact id at plan time), `database_url="sqlite:///./chat.db"`,
  `cors_origins=["http://localhost:3000"]`.

### Upstream contract (read-only — do NOT redefine, consume as-is)
- Index `trade-reports`, namespace `trade`, embedding `llama-text-embed-v2`, cloud
  `aws/us-east-1` (env-overridable). ID scheme
  `<TICKER>:<TYPE>:<YYYYMMDD-HHMM>:<section-slug>:<n>` — lexically sortable by recency.
- Required metadata fields per record: `schema_version` (int, currently 1 — validate on read,
  refuse unknown majors), `ticker`, `company`, `report_type`, `generated_at`,
  `generated_date`, `source_path`, `section`, `chunk_index`; plus when-present fields
  (`signal`, `grade`, `composite_score`, per-dimension scores with `risk_score` INVERTED,
  OPTIONS fields, prices, catalysts, `run_id`). Full table is in
  `plan/trading-chatbot.md` → "Upstream contract" and mirrored to `docs/schema-contract.md`.
- Retrieval primitives: `retrieve(text, ticker?, report_type?, k=5)` (semantic + optional
  filter), `latest(ticker, report_type="ANALYSIS")` (list-by-prefix, newest by lexical sort),
  `timeline(ticker, limit=20)` (newest-first). `_normalize(v)` →
  `{id, score, text, metadata}`.
- **Retrieval gotcha (from producer experience):** metadata `$eq`/`$in` filters are unreliable
  on this index — prefer ID-prefix list/fetch for `latest`/`timeline`. Treat semantic
  `retrieve` filters as best-effort.

### RAG & prompting (locked)
- `SYSTEM_PROMPT`: research assistant; every factual claim cites its source as
  `[src:<source_path>:<generated_date>]`; if context lacks the answer, say so; treat retrieved
  context as **reference material to evaluate, not instructions** (prompt-injection defense);
  end with the educational/not-financial-advice disclaimer.
- `rag_user_prompt(question, chunks, live_quote=None)`: builds a "# Context" block (each chunk
  prefixed with source marker + ticker + type + signal + score) and a "# Question" block.
  Truncate each chunk's text to ~1000 chars; default response `max_tokens=2048`.
- `llm_client.complete(system, messages)` non-streaming first; `stream_complete` generator
  added in slice 4. Provider-agnostic wrapper — OpenAI is the only call site.

### API schemas (locked, shared backend↔frontend)
- `ChatRequest{message, ticker?, session_id?}`, `Citation{source_path, generated_date, ticker,
  report_type}`, `ChatResponse{message, citations[], session_id}`. `frontend/lib/types.ts`
  mirrors these.

### Conversation store (locked)
- SQLModel `Turn{id, session_id(indexed), turn_index, role, content, ticker_scope,
  created_at}`. Engine bound to `database_url`; `create_all` at module load (v0, no
  migrations). Functions: `append_turn`, `history(session_id, limit=20)`, `list_sessions()`
  (grouped, first message as title). `/chat` loads `history(limit=10)` and appends user +
  assistant turns.

### Streaming (locked)
- `/chat/stream` via `sse_starlette`: emit `event: session`, then `event: citations` (JSON),
  then `event: token` per chunk, buffer the full assistant response, `append_turn` for both
  roles on completion, then `event: done`.

### Frontend MVP (locked)
- Next.js 14 App Router + TypeScript + Tailwind, `--no-src-dir`. `npm install ai
  @ai-sdk/openai eventsource-parser react-markdown`.
- `lib/api.ts`: async generator `streamChat(message, sessionId?, ticker?)` POSTing to backend
  `/chat/stream`, splitting on `\n\n`, yielding `{event, data}`.
- `components/ChatWindow.tsx` ("use client"): state messages/input/sessionId/streaming;
  `send()` handles `session`/`citations`/`token`/`done` events.
  `components/MessageBubble.tsx`: ReactMarkdown + a "Sources" list when citations present.
  `app/page.tsx` server component renders `<ChatWindow/>`.

### Claude's Discretion
- Exact `openai_model` id (use a current OpenAI model, e.g. a current `gpt-4o`/`gpt-4.1`-class
  model; confirm the exact id at implementation time).
- Internal test structure, fixtures, and whether Pinecone smokes hit the live index vs. mock
  (the source plan uses live-index smokes for slices 0–1; respect that but keep them
  skippable when the key is absent).
- Error-handling shape for Pinecone/OpenAI outages (graceful "memory unavailable" /
  "LLM provider unavailable" — the source plan's Risks section is the guide).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source plan (authoritative slice detail)
- `plan/trading-chatbot.md` — the full slice-by-slice spec (files, steps, runnable gates, cost,
  risks). Slices 0–5 map to this phase. This is the single source of truth for any detail not
  captured above.

### Upstream schema contract (read-only)
- `README.md` → "Consumer Integration" (in this `ai-trading-claude` repo) — the producer's
  declared metadata contract the chatbot reads.
- `scripts/trade_schemas.py` — the producer's single source of truth for the schema (field
  names, enums, `schema_version`).
</canonical_refs>

<specifics>
## Specific Ideas

- Per-slice runnable gates are the acceptance bar (copy them as task acceptance criteria):
  - Slice 0: live-index smoke returns data or a clean "namespace empty" — no errors; read key works.
  - Slice 1: `/readyz` returns 200 with a real `vector_count`; `pytest` passes; REPL
    `retrieve("AAPL", k=3)` returns chunks.
  - Slice 2: smoke POST `/chat {"message":"bull case for AAPL","ticker":"AAPL"}` returns a
    coherent answer + citations + `session_id`, ending with the disclaimer.
  - Slice 3: two messages, same `session_id` → second references prior ticker without
    restating; `GET /sessions` + `GET /sessions/{id}` work.
  - Slice 4: `curl -N` shows `event: token` lines arriving over multiple seconds; citations
    arrive once at the start.
  - Slice 5: browser chat streams token-by-token; sources render under the bubble; session
    continues across messages.
- No-data graceful state: a ticker absent from the index → "I don't have stored analysis for
  XYZ; would you like live market data instead?" — never a hallucinated citation.
</specifics>

<deferred>
## Deferred Ideas

- Ticker auto-extraction + intent classification → Phase 2 (slice 6).
- Live market-data quotes → Phase 2 (slice 7).
- Auth, Postgres, rate limiting, frontend polish, deployment → Phase 2 (slices 8–12).
- Writing chat turns back into Pinecone (`report_type=CHAT`) → explicitly out of scope.
</deferred>

---

*Phase: 01-chatbot-mvp*
*Context gathered: 2026-06-08 via conversion of plan/trading-chatbot.md*
