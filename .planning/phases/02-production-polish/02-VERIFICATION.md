---
phase: 02-production-polish
verified: 2026-06-11T00:30:00Z
status: passed
score: 8/8 must-haves verified (human items confirmed via 02-UAT.md re-test on 2026-06-11)
overrides_applied: 0
resolution: "human_verification items resolved through conversational UAT (02-UAT.md): 11 passed, 0 issues, 1 skipped (RATE-01 covered by unit tests). POLISH-01 UI flow and DEPLOY-01 confirmed pass. Three UAT-discovered defects (coreference stale ticker, no-data affirmative wrong ticker, empty sidebar) were fixed by gap-closure plans 02-08 + 02-09 and re-verified."
human_verification:
  - test: "End-to-end UI flow: sidebar session list + click-to-restore + citation cards + quote card + ticker chips (POLISH-01)"
    expected: "Refresh shows sessions in sidebar; clicking restores full history; citations expand; quote card distinct; tickers highlighted"
    why_human: "Frontend build passes but visual rendering, interaction behaviour, and cross-reload persistence require a running stack with real data"
  - test: "Live deploy: public URL serves stack end-to-end (DEPLOY-01 — human-action gate)"
    expected: "Public frontend URL responds; magic-link login works; 'bull case for AAPL' returns streamed cited answer through deployed stack"
    why_human: "Platform auth, secret configuration, and deploy commands must be performed by the user; Claude cannot authenticate to Fly.io/Vercel or access production env"
---

# Phase 02: Production Polish Verification Report

**Phase Goal:** Harden the Phase 1 chatbot MVP into a multi-user, deployable product — automatic ticker/intent extraction, live market-data quotes, magic-link auth + per-user isolation, Postgres migration, rate limiting + cost tracking, frontend polish, and containerized deployment + CI schema gate.
**Verified:** 2026-06-09T20:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Approach

Goal-backward verification against all 8 requirement IDs (TICK-01, QUOTE-01, AUTH-01, DB-01, RATE-01, POLISH-01, DEPLOY-01, VERIFY-SCHEMA). Backend test suite run live. Key source files read directly. SUMMARY.md claims treated as leads, not evidence.

---

## Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Messages with no explicit ticker resolve to the correct symbol before retrieval; intent classified; follow-up coreference preserved (TICK-01) | VERIFIED | `ticker_extractor.py` exports `extract_tickers()` with regex + LLM fallback; `intent_classifier.py` exports `classify_intent()` with five-label fixed-schema LLM call; `routes/chat.py` lines 136–155 implement 3-tier resolution: explicit > extracted > coreference via `ticker_scope` inheritance |
| 2 | "what's AAPL trading at?" returns live quote (price, day_change_pct, volume, timestamp, source); outlook questions return cited memory only; quotes cached ~15 min (QUOTE-01) | VERIFIED | `market_data.py` exports `quote()` with `_CACHE_TTL_SECONDS=900`, `_fetch_raw()` via yfinance; `routes/quote.py` registers `GET /quote/{ticker}`; `chat.py` `_wants_live_quote()` gates on intent=="factual" + price keywords + resolved ticker; `prompts.py` injects `## Live Quote` inset when `live_quote` is not None |
| 3 | Magic-link email issues 24h JWT; unauthenticated /chat returns 401; logged-in user sees only their sessions (AUTH-01) | VERIFIED | `auth.py` implements `issue_jwt()` (24h HS256), `verify_magic_token()` (15-min), `get_current_user()` via `Header()` dependency raising 401 on failure; `routes/auth.py` has `POST /auth/request-link` + `GET /auth/callback`; `chat.py` + `sessions.py` both use `Depends(get_current_user)`; `session_store.py` `list_sessions(user_id)` and `history(..., user_id=...)` enforce ownership |
| 4 | Postgres-switchable database_url leaves chat flow unchanged; `retrieved_chunk_ids` audit column exists on Turn (DB-01) | VERIFIED | `docker-compose.yml` has Postgres 16-alpine service with named volume + healthcheck; `.env.example` has commented `postgresql+psycopg://` DSN; `session_store.py` line 60: `retrieved_chunk_ids: Optional[list[str]] = Field(default=None, sa_column=Column(JSON))`; `chat.py` populates `chunk_ids=[c["id"] for c in chunks]` on data path |
| 5 | Exceeding per-user daily budget returns 429 + retry-after header; budget resets midnight UTC; /admin/budgets shows usage (RATE-01) | VERIFIED | `rate_limiter.py` has `UserBudget` SQLModel table; `check_and_increment()` raises `BudgetExceeded` with `retry_after_seconds`; `chat.py` lines 123–128 and 405–410 catch `BudgetExceeded` and raise HTTP 429 with `Retry-After` header before SSE stream opens; `routes/admin.py` exposes `GET /admin/budgets` behind `X-Admin-Token` gate |
| 6 | Sidebar lists prior sessions; clicking restores full history; citation cards expand; ticker chips highlight tickers; distinct QuoteCard for live quotes (POLISH-01) | UNCERTAIN | Code artifacts all exist and `npm run build` succeeds (5 routes compiled); `SessionList.tsx` fetches `GET /sessions` with Bearer on mount; `CitationCard.tsx` has expand toggle; `QuoteCard.tsx` renders price/day_change_pct/volume/timestamp/source with "~15 min delayed"; `TickerChip.tsx` renders as pill; `StreamingMarkdown.tsx` has 80ms debounce; `ChatWindow.tsx` handles SSE quote event — but "refresh → sessions visible → click → history restored" is a live-stack interaction requiring human verification |
| 7 | Backend and frontend run from Dockerfiles; secrets in deploy platform; CI runs VERIFY-SCHEMA on every commit (DEPLOY-01 + VERIFY-SCHEMA code artifacts) | VERIFIED | `backend/Dockerfile` multi-stage (uv builder → python:3.12-slim-bookworm, CMD runs uvicorn); `frontend/Dockerfile` node:20-alpine builder → runtime, `NEXT_PUBLIC_API_BASE` as ARG; `docker-compose.production.yml` secrets via `${VAR}` placeholders; `.github/workflows/ci.yml` triggers on push + PR, backend job passes `PINECONE_READ_KEY: ${{ secrets.PINECONE_READ_KEY }}` in env block; CI YAML valid; docker-compose.yml valid (COMPOSE_VALID) |
| 8 | Public URL serves stack end-to-end; chat works through deployed services (DEPLOY-01 live gate) | UNCERTAIN (human_needed) | Deployment artifacts authored and committed; human-action checkpoint documented in 02-07-SUMMARY.md as PENDING — user must authenticate platform CLIs, set secrets, and run deploy commands; no public URL confirmed yet |

**Score:** 6/8 truths directly VERIFIED in code; 2 require human action (POLISH-01 UI behavior + DEPLOY-01 live gate)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `trading-chatbot/backend/src/ticker_extractor.py` | extract_tickers() regex + LLM fallback | VERIFIED | 148 lines; KNOWN_TICKERS allowlist; false-positive guard for 1-char; LLM fallback fires only on regex miss |
| `trading-chatbot/backend/src/intent_classifier.py` | classify_intent() -> {intent, tickers} | VERIFIED | Intent literal; graceful JSON-decode fallback to factual; complete re-exported for monkeypatching |
| `trading-chatbot/backend/tests/test_schema_contract.py` | VERIFY-SCHEMA regression test | VERIFIED | Asserts ticker, report_type, generated_at, generated_date, source_path; marked @pytest.mark.live_index; auto-skips without PINECONE_READ_KEY |
| `trading-chatbot/backend/src/market_data.py` | quote() yfinance wrapper + 15-min TTL | VERIFIED | _CACHE_TTL_SECONDS=900; _fetch_raw() monkeypatch target; QuoteUnavailableError wraps all provider errors |
| `trading-chatbot/backend/src/routes/quote.py` | GET /quote/{ticker} endpoint | VERIFIED | APIRouter; 503 on QuoteUnavailableError; registered in main.py |
| `trading-chatbot/backend/src/auth.py` | Magic-link + JWT + get_current_user | VERIFIED | issue_jwt (24h HS256); verify_magic_token (15-min); get_current_user via Header() raising 401 |
| `trading-chatbot/backend/src/routes/auth.py` | POST /auth/request-link + GET /auth/callback | VERIFIED | router registered in main.py; email send wrapped for 503 on failure |
| `trading-chatbot/docker-compose.yml` | Postgres service for local multi-user | VERIFIED | postgres:16-alpine; pgdata volume; healthcheck pg_isready; docker compose config -q passes |
| `trading-chatbot/backend/src/session_store.py` | Turn.retrieved_chunk_ids + user_id + list_sessions(user_id) | VERIFIED | user_id indexed column; retrieved_chunk_ids Column(JSON); list_sessions filters by user_id; history enforces ownership |
| `trading-chatbot/backend/src/rate_limiter.py` | UserBudget table + check_and_increment + BudgetExceeded | VERIFIED | Midnight-UTC reset via _now() patchable helper; raises BudgetExceeded with retry_after_seconds |
| `trading-chatbot/backend/src/routes/admin.py` | GET /admin/budgets | VERIFIED | X-Admin-Token gate; current_usage() call; registered in main.py |
| `trading-chatbot/frontend/components/SessionList.tsx` | Sidebar session list + click-to-restore | VERIFIED (code) | fetchSessions() on mount with Bearer; click calls fetchSessionTurns + onSelectSession callback |
| `trading-chatbot/frontend/components/QuoteCard.tsx` | Distinct live quote card | VERIFIED (code) | Blue-tinted distinct styling; shows price/day_change_pct/volume/timestamp/source; "~15 min delayed" note |
| `trading-chatbot/frontend/components/CitationCard.tsx` | Expandable citation cards | VERIFIED (code) | expand/collapse toggle; chunkText optional; disabled when absent |
| `trading-chatbot/frontend/components/TickerChip.tsx` | Ticker pill highlighting | VERIFIED (code) | Monospace blue pill; aria-label; used in MessageBubble + StreamingMarkdown |
| `trading-chatbot/frontend/components/StreamingMarkdown.tsx` | Debounced incremental markdown rendering | VERIFIED (code) | 80ms debounce via useEffect+setTimeout; flushes on streaming=false; no rehype-raw |
| `trading-chatbot/backend/Dockerfile` | Multi-stage uv build + uvicorn CMD | VERIFIED | uv builder stage; python:3.12-slim-bookworm runtime; non-root user; CMD runs uvicorn with PORT |
| `trading-chatbot/frontend/Dockerfile` | Next.js production build image | VERIFIED | node:20-alpine; npm ci + npm run build; NEXT_PUBLIC_API_BASE as ARG; non-root user |
| `trading-chatbot/.github/workflows/ci.yml` | CI with pytest + VERIFY-SCHEMA + frontend build/lint | VERIFIED | Triggers push + PR; PINECONE_READ_KEY in env block; uv run pytest; npm ci + build + lint; CI_YAML_VALID |
| `trading-chatbot/docs/deployment.md` | One-command deploy per service | VERIFIED | File exists; DOCS_OK; covers Fly.io/Railway backend, Vercel frontend, secrets table, smoke checklist |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| routes/chat.py | ticker_extractor.py | extract_tickers() called before retrieve() | VERIFIED | Lines 138 (post_chat) + 284 (post_chat_stream); extracted tickers feed 3-tier resolution |
| routes/chat.py | intent_classifier.py | classify_intent() called before retrieve() | VERIFIED | Lines 140 (post_chat) + 286 (post_chat_stream); intent feeds _wants_live_quote() gate |
| routes/chat.py | market_data.py | quote() called when intent indicates price question | VERIFIED | _wants_live_quote() helper; lines 186–192 (post_chat) + 352–362 (stream); graceful QuoteUnavailableError path |
| main.py | routes/quote.py | app.include_router(quote_router) | VERIFIED | Line 38 in main.py |
| routes/chat.py | auth.py | Depends(get_current_user) gating /chat + /chat/stream | VERIFIED | Lines 104 (post_chat) + 253 (post_chat_stream) |
| session_store.py | Turn.user_id | user_id column + list_sessions(user_id) filter | VERIFIED | Field(default="", index=True); list_sessions filters Turn.user_id == user_id |
| config.py | postgresql+psycopg | database_url switchable to Postgres DSN | VERIFIED | Default sqlite:///./chat.db; .env.example has commented postgres DSN; pydantic-settings reads DATABASE_URL |
| routes/chat.py | Turn.retrieved_chunk_ids | append_turn records retrieved chunk ids | VERIFIED | Line 239–240 (post_chat): retrieved_chunk_ids=chunk_ids; line 394–395 (stream) |
| routes/chat.py | rate_limiter.py | check_and_increment(user_id) before LLM work | VERIFIED | Lines 123–128 (post_chat) + 405–410 (stream); 429 + Retry-After on BudgetExceeded |
| routes/admin.py | rate_limiter.py | current_usage() reads UserBudget table | VERIFIED | Line 67 in admin.py |
| .github/workflows/ci.yml | tests/test_schema_contract.py | CI runs VERIFY-SCHEMA with PINECONE_READ_KEY | VERIFIED | env: block line 65; when secret present, live_index test executes assertions |
| frontend/Dockerfile | backend URL | NEXT_PUBLIC_API_BASE ARG + ENV | VERIFIED | ARG + ENV at lines 24–25; set to placeholder in CI (line 99 of ci.yml); injected at deploy time |
| SessionList.tsx | /sessions | fetch GET /sessions with Bearer; click -> GET /sessions/{id} | VERIFIED (code) | fetchSessions() + fetchSessionTurns() in lib/api.ts; both send Authorization Bearer header |
| QuoteCard.tsx | event: quote | ChatWindow parses SSE quote event into QuoteCard | VERIFIED (code) | ChatWindow handles event.event === "quote"; attaches Quote to current assistant message; MessageBubble renders QuoteCard |

---

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| SessionList.tsx | sessions state | fetchSessions() → GET /sessions with Bearer | Yes — backend queries Turn table filtered by user_id | FLOWING |
| QuoteCard.tsx | quote prop | ChatWindow SSE handler for event: quote | Yes — market_data.quote() fetches yfinance with 15-min TTL cache | FLOWING |
| CitationCard.tsx | citation prop | MessageBubble maps chunks from SSE citations event | Yes — pinecone_client.retrieve() returns real chunks | FLOWING |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend test suite green | `cd trading-chatbot/backend && uv run pytest -q` | 135 passed, 7 skipped (live_index x5, postgres x1, schema-contract x1), 2 warnings | PASS |
| Frontend build succeeds | `cd trading-chatbot/frontend && npm run build` | Compiled successfully; 5 routes (/, /_not-found, /auth/callback, /login, 404); no type errors | PASS |
| docker-compose.yml valid | `docker compose config -q` | COMPOSE_VALID | PASS |
| CI YAML parses | `uv run python -c "import yaml; yaml.safe_load(...)"` | CI_YAML_VALID | PASS |
| deployment.md exists with deploy content | `test -f ... && grep -qi "deploy"` | DOCS_OK | PASS |

---

## Probe Execution

No probe-*.sh files declared or found in this phase.

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TICK-01 | 02-01 | No-ticker message resolves to symbol; intent classified; coreference | VERIFIED | extract_tickers() + classify_intent() wired in both /chat endpoints; 3-tier ticker resolution in chat.py; 135 passing tests include TICK-01 cases |
| QUOTE-01 | 02-02 | Live quote on price intent; cited memory on outlook; ~15-min cache | VERIFIED | market_data.py quote() + yfinance + 900s TTL; _wants_live_quote() gate; GET /quote/{ticker}; prompts.py Live Quote inset |
| AUTH-01 | 02-03 | 24h JWT on magic-link; 401 unauthenticated; per-user isolation | VERIFIED | auth.py full implementation; chat + sessions gated by Depends(get_current_user); user_id column + ownership enforcement |
| DB-01 | 02-04 | Postgres-switchable; chat flow unchanged; retrieved_chunk_ids audit column | VERIFIED | docker-compose.yml; .env.example postgres DSN; Turn.retrieved_chunk_ids Column(JSON); parity tests pass |
| RATE-01 | 02-05 | 429 + retry-after on budget exceed; midnight-UTC reset; /admin/budgets | VERIFIED | UserBudget table; check_and_increment raises BudgetExceeded; chat.py enforces before LLM work; /admin/budgets behind X-Admin-Token |
| POLISH-01 | 02-06 | Sidebar session list + restore; expandable citations; ticker chips; distinct QuoteCard | UNCERTAIN (human_needed) | All components authored and build passes; interactive behavior (refresh → sidebar → click → restore) needs running stack |
| DEPLOY-01 | 02-07 | Dockerfiles; secrets in platform; public URL end-to-end | PARTIAL | Dockerfiles + production compose + CI = VERIFIED in code; live deploy = human_needed (user must run deploy commands) |
| VERIFY-SCHEMA | 02-01 + 02-07 | Regression test asserts required metadata fields; runs in CI | VERIFIED | test_schema_contract.py asserts ticker/report_type/generated_at/generated_date/source_path; wired in ci.yml with PINECONE_READ_KEY secret |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | No TBD/FIXME/XXX markers in any phase-02 modified files | — | Clean |
| `CitationCard.tsx` | 28 | `cast to unknown as Record` to access `chunk_text` not in `Citation` type | Info | The current Citation type lacks `chunk_text`; CitationCard degrades gracefully (no expand button when absent) — this is documented as correct behavior given backend schema |

No blocker debt markers found. No stub patterns found. No hardcoded secrets found in Dockerfiles or compose.

---

## Human Verification Required

### 1. POLISH-01: Polished frontend end-to-end (slice 11 runnable gate)

**Test:** Run backend (`cd trading-chatbot/backend && uv run uvicorn src.main:app --reload`) and frontend (`cd trading-chatbot/frontend && npm run dev`); log in via the magic link flow. Then:
1. Ask "bull case for AAPL" — verify streamed answer with expandable CitationCards in Sources section
2. Ask "what's AAPL trading at?" — verify a distinct blue QuoteCard with price + timestamp + "~15 min delayed" appears above the answer text
3. Start a second session ("compare NVDA and AMD") — verify ticker chips highlight NVDA/AMD in the assistant message
4. Refresh the page — verify sidebar lists both sessions — click the first — verify full history is restored

**Expected:** All 4 steps pass; sidebar cross-reload persistence works; QuoteCard visually distinct from citations
**Why human:** Interactive rendering, SSE event rendering in browser, cross-reload state via localStorage + session fetch, and visual distinction cannot be verified programmatically. Frontend build passes but UI correctness requires a running stack.

### 2. DEPLOY-01: Live deploy to public URL (slice 12 human-action gate)

**Test:** Per `docs/deployment.md`:
1. Authenticate Fly.io/Railway CLI (`fly auth login` or Railway login) and Vercel (`vercel login`)
2. Set all platform secrets (PINECONE_READ_KEY, OPENAI_API_KEY, JWT_SECRET, RESEND_API_KEY, DATABASE_URL pointing to managed Postgres, NEXT_PUBLIC_API_BASE pointing at backend URL, CORS_ORIGINS)
3. Deploy backend then frontend (one command each per deployment.md)
4. Visit the public frontend URL, log in via magic link, send "bull case for AAPL", confirm a streamed cited response end-to-end through the deployed stack

**Expected:** Public frontend URL serves the app; magic-link login works; cited streamed response arrives
**Why human:** Platform authentication, account provisioning, secret management, and deploy commands require human action — Claude cannot authenticate to external platforms or access production credentials.

---

## Gaps Summary

No code gaps found. All 8 requirements have substantive implementations in the codebase. The two human_needed items are intentional human-action gates documented in the plans (02-06 Task 4 checkpoint and 02-07 Task 2 checkpoint):

- **POLISH-01** frontend components are fully wired and the build passes. The human checkpoint is a visual + interactive UI verification requiring a running stack — not a code defect.
- **DEPLOY-01** deployment artifacts (Dockerfiles, CI, production compose, docs) are all authored and validated. The live-deploy step is a human-action gate that requires platform accounts and secrets — explicitly marked as pending in 02-07-SUMMARY.md.

The REQUIREMENTS.md still shows `[ ]` (unchecked) for TICK-01, POLISH-01, DEPLOY-01, and VERIFY-SCHEMA — these checkboxes reflect the state of the requirements file document, not the code. The implementations all exist in the codebase (TICK-01 verified; VERIFY-SCHEMA verified; POLISH-01 and DEPLOY-01 pending their human checkpoints).

---

_Verified: 2026-06-09T20:00:00Z_
_Verifier: Claude (gsd-verifier)_
