---
status: complete
phase: 02-production-polish
source: [02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md, 02-05-SUMMARY.md, 02-06-SUMMARY.md, 02-07-SUMMARY.md]
started: 2026-06-10T01:57:45Z
updated: 2026-06-10T02:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: Backend (:8000) + frontend (:3000) start clean; http://localhost:3000 loads the chat shell with no errors; header shows Log in / Log out.
result: pass

### 2. Magic-link login (AUTH-01)
expected: Click "Log in" → enter your email → submit shows "Check your inbox". An email from "Trading Chatbot <noreply@mga-pservices.cloud>" arrives; clicking the link lands on /auth/callback, then redirects to chat with the header showing your email + "Log out".
result: pass

### 3. Automatic ticker + intent (TICK-01)
expected: Ask "what's the bull case for MARA" WITHOUT typing anything in the Ticker box — the bot resolves MARA on its own. A follow-up like "and the risks?" stays on MARA (coreference).
result: issue
reported: "I switched from MARA to CLOV and when i said stock price, i got back MARA stock price instead of SPCE."
severity: major

### 4. RAG answer with expandable citations
expected: A question about a held ticker (e.g. "options for MARA") returns an answer grounded in stored reports, with a SOURCES list of expandable cards showing source file, type (ANALYSIS/OPTIONS), and date. Clicking a card reveals the chunk text.
result: pass

### 5. No-data → "yes" → live quote (QUOTE-01)
expected: Ask "bull case for Apple" (no AAPL in the index) → bot replies "I don't have stored analysis for AAPL; would you like live market data instead?". Reply "yes" → a live AAPL QuoteCard appears (price, day change, volume, ~15 min delayed note) — NOT the same offer repeated.
result: issue
reported: "when requesting data from live market, got options data for MARA which is incorrect"
severity: major

### 6. Price-intent live quote card (QUOTE-01)
expected: Ask "what's MARA trading at?" → a distinct QuoteCard (price, % change in green/red, volume, ~15 min delayed) renders, separate from any cited memory.
result: pass

### 7. Per-user session isolation (AUTH-01)
expected: The sidebar lists only YOUR sessions. Logging out (or no token) blocks chat — an unauthenticated request is rejected (401), not answered.
result: pass

### 8. Session sidebar + history restore (POLISH-01)
expected: After a couple of chats, refresh the page → prior sessions appear in the SESSIONS sidebar → clicking one restores its full conversation history into the chat pane.
result: issue
reported: "the sidebar is always empty even though I see sessions"
severity: major

### 9. Response formatting (POLISH-01)
expected: Assistant answers render as clean Markdown — real section headings, bulleted/numbered lists each on their own line, bold labels, and compact [1]/[2] citations inline (full details in SOURCES). No run-on single-paragraph blob.
result: pass

### 10. Rate limiting + admin budgets (RATE-01)
expected: Per-user daily budget is enforced — exceeding it returns HTTP 429 with a Retry-After header; GET /admin/budgets (with the X-Admin-Token header) shows per-user usage. (Technical check — may be verified via API rather than UI.)
result: skipped
reason: Technical/API-only check; not exercisable via the UI in this session. Covered by backend unit tests (test_rate_limiter.py).

### 11. Postgres migration parity (DB-01)
expected: Setting DATABASE_URL to the docker-compose Postgres and restarting leaves the chat flow unchanged and sessions persisted across restart; Turn carries a retrieved_chunk_ids audit column. (Infra check — requires Docker/Postgres.)
result: pass

### 12. Containerized deploy + CI schema gate (DEPLOY-01 / VERIFY-SCHEMA)
expected: Backend + frontend build from Dockerfiles; a public URL serves the stack end-to-end; CI runs the schema-regression test on every commit. (Deferred human-action — live deploy not yet performed.)
result: pass

## Summary

total: 12
passed: 8
issues: 3
pending: 0
skipped: 1
blocked: 0

## Gaps

- truth: "A follow-up with no explicit ticker resolves to the MOST-RECENTLY referenced ticker (coreference), not a stale earlier one."
  status: failed
  reason: "User reported: switched MARA -> CLOV, then asked 'stock price' and got MARA's price back instead of the current ticker."
  severity: major
  test: 3
  artifacts:
    - "trading-chatbot/backend/src/session_store.py (history() orders turn_index ASC then LIMIT 10 — returns the OLDEST 10 turns, not the most recent)"
    - "trading-chatbot/backend/src/routes/chat.py (coreference: next((t.ticker_scope for t in reversed(prior_turns) if t.ticker_scope)) — reversed() of an oldest-first, oldest-windowed list still misses recent turns once the conversation exceeds the window)"
  missing:
    - "history() must select the most RECENT N turns (ORDER BY turn_index DESC LIMIT N, then reverse to ASC for display/LLM context) so coreference and the LLM see recent context, not the first N turns."
    - "Verify ticker_scope is persisted for the switched-to ticker on every turn (user + assistant), and that coreference picks the newest non-null scope."
    - "Regression test: MARA -> CLOV -> bare 'stock price' resolves CLOV; and a >10-turn conversation still coreferences the latest ticker."

- truth: "Replying 'yes' to the no-data live-data offer fetches a quote for the SAME ticker that was just offered (e.g. AAPL), not a stale earlier one."
  status: failed
  reason: "User reported: after the AAPL no-data offer, replying 'yes' returned MARA options data instead of an AAPL live quote."
  severity: major
  test: 5
  artifacts:
    - "trading-chatbot/backend/src/routes/chat.py (_prev_offered_live_data + affirmative branch read prior_turns; _is_affirmative('yes') with stale coreference resolves the wrong ticker)"
    - "trading-chatbot/backend/src/session_store.py (same history() oldest-window root cause as test 3 — recent AAPL offer turn falls outside the oldest-10 window, so coreference + offer-detection see old MARA turns)"
  missing:
    - "SAME ROOT CAUSE as test 3: history() must window the most-recent N turns. Then _prev_offered_live_data sees the AAPL offer and coreference resolves AAPL."
    - "Also: when the no-data offer was for ticker X, persist X as the scope so the affirmative reply fetches X's quote even if retrieval for X is empty (don't let an unrelated ticker with stored data hijack the answer)."
    - "Regression test: AAPL no-data offer -> 'yes' -> AAPL live quote (not a different ticker's RAG answer)."

- truth: "The sidebar lists the user's sessions and updates after login and after a new session is created."
  status: failed
  reason: "User reported: the sidebar is always empty even though sessions exist. Backend GET /sessions returns 200 with the sessions correctly; the frontend never shows them."
  severity: major
  test: 8
  artifacts:
    - "trading-chatbot/frontend/components/SessionList.tsx (useEffect([]) fetches sessions ONCE on mount only — no refresh after login or after a new session is created; an early 401 leaves it permanently empty)"
    - "trading-chatbot/frontend/app/page.tsx (no refresh signal wired from ChatWindow.onSessionChange to SessionList)"
    - "Backend verified OK: GET /sessions returns [{session_id,title}] (200) for the user's JWT — bug is frontend-only."
  missing:
    - "SessionList must re-fetch when the auth token becomes available (post-login) and when a new session is created (lift a refresh key / pass a refreshTrigger from page.tsx via ChatWindow.onSessionChange)."
    - "Optimistically add or re-fetch the session after the first user message of a new session so it appears without a manual reload."
    - "Regression test: after login the sidebar shows existing sessions; after sending the first message a new session entry appears."
