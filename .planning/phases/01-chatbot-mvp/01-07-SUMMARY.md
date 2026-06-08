---
phase: 01-chatbot-mvp
plan: "07"
subsystem: frontend/sse-parser + ticker-wiring
gap_closure: true
tags: [sse, crlf, vitest, coreference, ticker, nextjs, regression-test]

dependency_graph:
  requires:
    - phase: 01-06
      provides: Next.js streaming chat frontend (streamChat async generator + ChatWindow SSE handling)
    - phase: 01-05
      provides: POST /chat/stream SSE endpoint (sse-starlette, CRLF wire format)
  provides:
    - trading-chatbot/frontend/lib/api.ts: CRLF-tolerant SSE parser — event split /\r\n\r\n|\n\n/, line split /\r?\n/
    - trading-chatbot/frontend/lib/api.test.ts: vitest CRLF regression tests A–D (locks the wire-format contract)
    - trading-chatbot/frontend/vitest.config.ts: vitest runner (node env, lib/**/*.test.ts)
    - trading-chatbot/frontend/components/ChatWindow.tsx: ticker input wired to streamChat 3rd arg (enables backend ticker_scope coreference)
  affects:
    - Phase 2 (slice 6 auto ticker/intent resolution supersedes the manual ticker input added here)

tech-stack:
  added:
    - vitest@^4.1.8 (devDep — frontend unit test runner; test/test:watch scripts)
  changed:
    - "next 14.2.29 -> 16.2.7, ai 3.2 -> 6.0.198, @ai-sdk/openai 0.0.68 -> 3.0.68 (baseline commit ahead of this plan; build/typecheck/tests all green on the upgraded toolchain)"
  patterns:
    - CRLF-tolerant SSE parsing — split events on /\r\n\r\n|\n\n/, field lines on /\r?\n/ (tolerates both CRLF and bare-LF wire)
    - Mocked fetch ReadableStream for testing an async-generator SSE consumer without a live server
    - Optional ticker scope hint kept across sends so no-ticker follow-ups inherit backend ticker_scope

key-files:
  created:
    - trading-chatbot/frontend/lib/api.test.ts (CRLF regression Tests A–D)
    - trading-chatbot/frontend/vitest.config.ts
  modified:
    - trading-chatbot/frontend/lib/api.ts (CRLF splitters + export parseSSEBlock + doc comment)
    - trading-chatbot/frontend/components/ChatWindow.tsx (ticker state + input + 3rd-arg streamChat call + hint copy)
    - trading-chatbot/frontend/package.json (vitest devDep + test scripts)

commits:
  - 5580057 chore(deps): upgrade frontend to Next 16 + Vercel AI SDK 6 (baseline)
  - 42d6d37 test(01-07): add failing CRLF SSE parser regression tests (vitest) [RED]
  - 57b328b fix(01-07): CRLF-tolerant SSE parser in streamChat/parseSSEBlock [GREEN]
  - 5f8af1b feat(01-07): wire ticker input into ChatWindow -> streamChat 3rd arg
  note: All code commits are in the NESTED trading-chatbot/ repo (branch main). This SUMMARY lives in the outer ai-trading-claude repo's .planning/.
---

# Plan 01-07 Summary — Gap Closure: CRLF SSE Parser + Ticker Wiring

## What this delivered

Closed the two frontend gaps the Phase 1 UAT (`01-UAT.md`) found, both FRONTEND-only —
the backend was verified correct via live curl + `xxd` wire capture. After this plan the
Phase 1 user story works end-to-end in a real browser (human-verified).

**Gap 1 (BLOCKER) — CRLF SSE parser.** sse-starlette emits CRLF-delimited events (`\r\n`
field lines, `\r\n\r\n` event separators), but the parser in `lib/api.ts` split on `\n\n` /
`\n`. No event parsed during streaming → empty bubble + infinite "Streaming response…"
spinner. Fix: event split `buffer.split("\n\n")` → `buffer.split(/\r\n\r\n|\n\n/)`; line
split `block.split("\n")` → `block.split(/\r?\n/)` (the latter strips the trailing `\r` that
produced the `event:"done\r"` / `"citations\r"` garble and broke `JSON.parse` of citations).
Event names, yield order, done-termination, prefix-stripping, and the drain-after-close path
are unchanged — only the two delimiters changed.

**Gap 2 (MAJOR) — ticker wiring.** The UI never sent a ticker, so backend `ticker_scope` was
never populated and coreference was dead. Added a `ticker` state + a dedicated short (`w-24`)
ticker `<input>` left of the message box (UPPERCASE+trimmed, `maxLength` 10, disabled while
streaming), and `send()` now passes `ticker.trim() || undefined` as the 3rd `streamChat` arg.
The ticker is not cleared on send and not required to send, so a no-ticker follow-up
("what about its risks?") inherits the prior ticker via the backend.

**Regression lock.** New vitest suite (`lib/api.test.ts`, Tests A–D) feeds the exact CRLF wire
bytes (including a chunk boundary that splits mid-`\r\n\r\n`) through a mocked fetch
ReadableStream and asserts the parsed events. Reverting either split to the old `\n`-only form
reproduces the RED failures, so the CRLF mismatch is now caught automatically.

## Verification

- **Automated:** `npm test` → 4 passed (CRLF Tests A–D green). `npx tsc --noEmit` clean.
  `npm run build` succeeds (Next.js 16.2.7 / Turbopack). RED→GREEN proven (A/B/D failed
  pre-fix; Test D showed the `event:"citations\r"` garble).
- **Browser E2E (human-verified, blocking checkpoint — approved):** With backend +
  `npm run dev` running: "bull case for MARA" streamed token-by-token (no infinite spinner)
  with a Sources list of real MARA citations; the same-session follow-up "what about its
  risks?" resolved to MARA without restating the ticker; both answers ended with the
  educational / not-financial-advice disclaimer. This is the exact gate the deferred 01-06
  "Task 3: browser human-verify" skipped — the gaps were browser-only, so unit tests alone
  were insufficient evidence.

## Requirements satisfied

STREAM-01 (token-by-token streaming visible in browser), UI-01 (chat UI renders streamed
answer + Sources), CONV-01 (no-ticker follow-up resolves prior ticker), CHAT-01 (grounded,
cited, disclaimer-terminated answer). Closes ROADMAP Phase 1 Success Criteria 1, 2, and 4 in
the browser.

## Deviations from plan

- **Dependency upgrade taken as a baseline.** The frontend had uncommitted, unplanned major
  dep bumps (Next 14→16, ai 3→6, @ai-sdk/openai 0→3) in the working tree. Per user decision,
  these were committed as a separate baseline (`5580057`) BEFORE this plan rather than
  stashed. The plan was written against Next 14; all work was re-validated on Next 16
  (`tsc`, `npm test`, `npm run build`, and the browser E2E all pass). `lib/api.ts` uses native
  `fetch`/`ReadableStream` (not the `ai` SDK), so the SDK 6 bump does not affect the parser.

## Deferred to Phase 2 (secondary findings, NOT in scope here)

1. `backend/.env` `CORS_ORIGINS=[http://localhost:3000]` is not valid JSON — tolerated on a
   normal `uv run` boot but would crash if exported to a real env. Fix: `["http://localhost:3000"]`
   and/or a string-splitting validator on `cors_origins` in `config.py`.
2. The streaming route runs blocking sync I/O (Pinecone search, OpenAI stream) on the event
   loop with no timeout. Not the cause of either gap. Fix: threadpool + stream/client timeout.

Both belong to Phase 2 (Production Polish), which already owns backend hardening.
