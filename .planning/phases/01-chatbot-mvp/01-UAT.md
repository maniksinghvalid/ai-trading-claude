---
status: diagnosed
phase: 01-chatbot-mvp
source: [01-01-SUMMARY.md, 01-02-SUMMARY.md, 01-03-SUMMARY.md, 01-04-SUMMARY.md, 01-05-SUMMARY.md, 01-06-SUMMARY.md]
mode: mvp
user_story: "As a trader, I want to chat about my holdings and ask follow-up questions that remember the prior ticker, so that I can trust the answer and verify it against the cited source reports."
started: 2026-06-08T20:59:49Z
updated: 2026-06-08T20:59:49Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[user-flow halted at Test 2 — diagnosed; 2 gaps found (both frontend). Fix plan pending. Tests 3–8 not reached.]

## Tests

### 1. Cold Start Smoke Test
expected: Kill any running backend/frontend. Start backend (`uv run uvicorn src.main:app --reload`, with PINECONE_READ_KEY + OPENAI_API_KEY set in backend/.env) and frontend (`npm run dev`) from scratch. Backend boots with no tracebacks and creates the SQLite Turn table on load; frontend compiles; http://localhost:3000 renders the chat UI with no console errors.
result: pass

### 2. Ask About a Holding (streaming)
expected: In the chat box type "bull case for MARA" and send. The answer appears token-by-token (streaming in, not all at once), and reads as a coherent response grounded in stored analysis.
result: issue
reported: "updated the text to 'bull case for MARA' and its not returning any response, FAIL"
severity: major

### 3. Cited Sources Render
expected: Under the assistant's answer, a "Sources" list appears citing the report(s) it drew from — each entry shows a source path, report type, and date (e.g. `[1] TRADE-ANALYSIS-MARA ... • ANALYSIS • 2026-...`).
result: [pending]

### 4. Follow-up Remembers the Ticker (coreference)
expected: In the same conversation, send "what about its risks?" WITHOUT naming MARA again. The answer is about MARA's risks — the chatbot remembers the prior ticker without you restating it.
result: [pending]

### 5. Educational Disclaimer Present
expected: The assistant's answers end with the educational / not-financial-advice disclaimer.
result: [pending]

### 6. No-Data Path (no fabricated source)
expected: [deferred technical check] Ask about a ticker with no stored reports, e.g. "tell me about ZZZZFAKE". You get a graceful message like "I don't have stored analysis for ZZZZFAKE..." with NO Sources list (no fabricated citation) — not an error or a hallucinated answer.
result: [pending]

### 7. Backend Health Endpoints
expected: [deferred technical check] `curl http://localhost:8000/healthz` → `{"status":"ok"}`; `curl http://localhost:8000/readyz` → status ok with a vector_count (proves the live Pinecone index is reachable). On a Pinecone failure /readyz returns a generic 503 with no key/stack leak.
result: [pending]

### 8. Coverage — Trust & Verify Outcome
expected: [coverage check] The user-story outcome holds: pick one cited source from Test 3 and confirm it points to a real report (its source_path / ticker / date are genuine, not invented), so the answer is verifiable against its source. Citations only ever appear when backed by real retrieved chunks.
result: [pending]

## Summary

total: 8
passed: 1
issues: 1
pending: 6
skipped: 0
blocked: 0

## Gaps

- truth: "Asking 'bull case for MARA' in the chat returns a streaming, coherent answer in the browser"
  status: failed
  reason: "User reported: 'bull case for MARA' returns no response — stuck on 'Streaming response…' spinner forever, empty bubble."
  severity: blocker
  test: 2
  root_cause: |
    Frontend SSE parser line-ending mismatch. sse-starlette emits CRLF-delimited
    events — confirmed via xxd of the live wire: every field line ends 0d0a (\r\n)
    and events are separated by 0d0a0d0a (\r\n\r\n). But frontend/lib/api.ts splits
    the stream buffer on "\n\n" (line ~110: `buffer.split("\n\n")`) and parseSSEBlock
    splits each block on "\n" (line ~32: `block.split("\n")`). "\n\n" never occurs
    inside "\r\n\r\n", so NO SSE event is parsed while streaming: tokens never
    accumulate, the assistant bubble stays empty, and `streaming` is never set false
    → infinite "Streaming response…" spinner. At stream close the drain path parses
    one garbled blob (event "done\r"), still rendering nothing.
    Backend VERIFIED CORRECT: `curl -N POST /chat/stream {"message":"bull case for MARA"}`
    streamed session → citations(6 real MARA records) → token… and completed in 6s.
    This is precisely the failure the deferred 01-06 "Task 3: browser human-verify"
    gate was meant to catch.
  artifacts:
    - path: "trading-chatbot/frontend/lib/api.ts"
      issue: "Event split on '\\n\\n' (~L110) and line split on '\\n' (~L32) — must handle CRLF (\\r\\n\\r\\n / \\r\\n) wire format from sse-starlette"
  missing:
    - "Split SSE events on /\\r\\n\\r\\n|\\n\\n/ (or normalize \\r\\n→\\n before splitting) in streamChat"
    - "Split block lines on /\\r?\\n/ (or strip trailing \\r) in parseSSEBlock"
  debug_session: "Diagnosed inline in verify-work via live curl reproduction + xxd wire capture (no separate debug session file)."

- truth: "Follow-up 'what about its risks?' remembers the prior ticker (MARA) — the user-story coreference outcome"
  status: failed
  reason: "Discovered during diagnosis: the frontend never sends a ticker, so backend ticker_scope is never populated and coreference cannot inherit the prior ticker. Will block Test 4 once Test 2 is fixed."
  severity: major
  test: 4
  root_cause: |
    Frontend never transmits a ticker. ChatWindow.send() calls `streamChat(text, sessionId)`
    (components/ChatWindow.tsx ~L72) with the 3rd `ticker` argument omitted, and there is
    NO ticker input in the UI — despite the empty-state hint "Pass a ticker explicitly —
    auto-extraction is Phase 2." Backend coreference (routes/chat.py) inherits the most
    recent non-null `ticker_scope` from history, but append_turn stores ticker=req.ticker,
    which is always None from the UI → ticker_scope is never set → a follow-up like
    "what about its risks?" retrieves with ticker=None (semantic-only) and cannot resolve
    to MARA. Coreference — the core of the user story — is dead in the real UI even though
    backend unit tests pass (they pass ticker explicitly). On the MARA send it "worked"
    only because the query text itself contained "MARA" so unscoped semantic search hit
    MARA chunks; a follow-up without the ticker word will not.
  artifacts:
    - path: "trading-chatbot/frontend/components/ChatWindow.tsx"
      issue: "No ticker captured from the user; streamChat called without the ticker arg (~L72)"
    - path: "trading-chatbot/frontend/lib/api.ts"
      issue: "streamChat accepts a ticker param that the caller never supplies"
  missing:
    - "Capture a ticker in the UI (dedicated input, or extract from the message) and pass it to streamChat as the 3rd arg"
    - "Verify ticker_scope is persisted (append_turn ticker=req.ticker) so a no-ticker follow-up inherits it via backend coreference"
  debug_session: "Diagnosed inline via code trace (ChatWindow.send → streamChat → backend append_turn)."

## Secondary findings (hardening — NOT blocking the user story; for the planner to weigh)

- CORS_ORIGINS in backend/.env is `[http://localhost:3000]` (not valid JSON). pydantic-settings
  decodes `cors_origins: list[str]` as a complex field via json.loads — the dotenv source
  tolerates it on a normal `uv run` boot (verified: clean boot returns healthz ok), BUT if
  CORS_ORIGINS is ever exported into the real environment the backend crashes on startup with
  SettingsError. Fix: use valid JSON `["http://localhost:3000"]` and/or a string-splitting
  field validator on cors_origins.
- Streaming route runs blocking sync I/O (Pinecone index.search, OpenAI stream=True) directly
  inside the async SSE generator on the event loop, with no timeout. Not the cause here (both
  upstreams responded fast), but any slow upstream would freeze the loop with no error backstop.
  Consider running blocking calls in a threadpool and adding a stream/client timeout.
