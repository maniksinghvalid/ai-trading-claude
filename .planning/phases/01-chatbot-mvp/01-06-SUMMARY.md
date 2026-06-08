---
phase: 01-chatbot-mvp
plan: "06"
subsystem: frontend/streaming-chat-ui
tags: [nextjs, react, typescript, tailwind, sse, react-markdown, streaming, xss-defense]

dependency_graph:
  requires:
    - phase: 01-05
      provides: POST /chat/stream SSE endpoint emitting session/citations/token*/done events
  provides:
    - frontend/package.json: Next.js 14 App Router project (TS + Tailwind, ai/@ai-sdk/openai/eventsource-parser/react-markdown)
    - frontend/lib/types.ts: Citation/ChatRequest/ChatResponse/StreamEvent/Message mirrors of backend schemas.py
    - frontend/lib/api.ts: streamChat async generator — POST /chat/stream, blank-line SSE split, yields {event,data}
    - frontend/components/ChatWindow.tsx: "use client" — session/citations/token/done/error event handling, sessionId continuity
    - frontend/components/MessageBubble.tsx: ReactMarkdown render + Sources list (no rehype-raw — XSS defense T-06-01)
    - frontend/app/page.tsx: server component rendering ChatWindow
    - frontend/.env.local.example: NEXT_PUBLIC_API_BASE=http://localhost:8000
  affects:
    - Phase 2 (slice 11 frontend polish — sidebar, CitationCard, SessionList, QuoteCard)

tech-stack:
  added:
    - next@14.2.29 (App Router, TypeScript, Tailwind)
    - react@18, react-dom@18
    - ai@^3.2.22, @ai-sdk/openai@^0.0.68 (declared; streamChat uses native fetch/ReadableStream)
    - eventsource-parser@^2.0.0 (declared; SSE parsing done inline in api.ts)
    - react-markdown@^9.0.1 (safe markdown render — no rehype-raw)
    - tailwindcss@^3.4.3, autoprefixer, postcss
    - typescript@^5, @types/node, @types/react, @types/react-dom
  patterns:
    - Async generator over ReadableStream for SSE consumption (no SSE library — native fetch)
    - Blank-line delimited SSE parsing: buffer.split('\n\n') with rolling buffer tail
    - "use client" ChatWindow with updateLastMessage pattern for streaming token accumulation
    - ReactMarkdown without rehype-raw: XSS defense for LLM output (T-06-01)
    - sessionId persisted in React state across sends for multi-turn coreference

key-files:
  created:
    - trading-chatbot/frontend/package.json (Next.js 14 + all deps)
    - trading-chatbot/frontend/next.config.mjs
    - trading-chatbot/frontend/tailwind.config.ts
    - trading-chatbot/frontend/tsconfig.json
    - trading-chatbot/frontend/postcss.config.mjs
    - trading-chatbot/frontend/next-env.d.ts
    - trading-chatbot/frontend/app/layout.tsx (Inter font, dark bg)
    - trading-chatbot/frontend/app/globals.css (Tailwind directives + chat-scroll)
    - trading-chatbot/frontend/app/page.tsx (server component, renders ChatWindow)
    - trading-chatbot/frontend/lib/types.ts (Citation/ChatRequest/ChatResponse/StreamEvent/Message)
    - trading-chatbot/frontend/lib/api.ts (streamChat async generator)
    - trading-chatbot/frontend/components/ChatWindow.tsx ("use client" streaming handler)
    - trading-chatbot/frontend/components/MessageBubble.tsx (ReactMarkdown + Sources list)
    - trading-chatbot/frontend/.env.local.example (NEXT_PUBLIC_API_BASE)
  modified:
    - trading-chatbot/.gitignore (added *.tsbuildinfo)

key-decisions:
  - "Native fetch + ReadableStream for SSE: eventsource-parser and ai SDK are declared in package.json per the locked dep list, but streamChat uses the native browser Fetch API with a ReadableStream reader and manual blank-line splitting. This avoids needing an EventSource (which only supports GET) and matches the locked POST /chat/stream contract."
  - "ReactMarkdown without rehype-raw (T-06-01): LLM output rendered via ReactMarkdown only. rehype-raw is not installed or imported. dangerouslySetInnerHTML is never used. This prevents XSS injection via crafted markdown from the LLM."
  - "sessionId in React state (not localStorage): Phase 1 is single-session — persisting across page refreshes is Phase 2 (auth + session sidebar). Keeping it in state is simpler and avoids unintended session leakage."
  - "updateLastMessage pattern: streaming tokens accumulate into the last message via a functional state updater (prev => [...prev.slice(0,-1), updater(last)]). This avoids stale closure issues common with direct state assignment inside async generators."
  - "App Router (no src-dir): --no-src-dir flag means app/ and components/ are at frontend root, not inside frontend/src/. Path aliases use @/* -> ./*."

patterns-established:
  - "SSE async-generator pattern: fetch POST → getReader() → decode → split on \\n\\n → parseSSEBlock → yield {event,data}"
  - "Streaming bubble accumulation: empty assistant message appended before loop; updateLastMessage called on each token event"

requirements-completed: [UI-01]

duration: ~20min
completed: 2026-06-08
---

# Phase 1 Plan 6: Next.js 14 Streaming Chat UI Summary

**Next.js 14 App Router streaming chat UI — async-generator SSE client, ChatWindow with live token accumulation, MessageBubble with Sources list, and session continuity across multi-turn messages.**

---

## Performance

- **Duration:** ~20 min
- **Started:** 2026-06-08T17:21:17Z
- **Completed:** 2026-06-08
- **Tasks:** 2 auto (+ 1 human-verify pending)
- **Files modified:** 14 created + 1 modified (.gitignore)

---

## Accomplishments

- `frontend/` bootstrapped as a standard Next.js 14 App Router + TypeScript + Tailwind project (`--no-src-dir` layout). All 14 files hand-authored and committed cleanly; `npm run build` compiles with 4/4 static pages; `npx tsc --noEmit` passes with zero errors.

- `lib/api.ts` exports `streamChat(message, sessionId?, ticker?)`: async generator that POSTs to `${NEXT_PUBLIC_API_BASE}/chat/stream`, reads the response via `ReadableStream`, splits on blank-line SSE delimiter, parses `event:` + `data:` lines, and yields `{event, data}` objects. Stops yielding after the `done` event. Backend URL defaults to `http://localhost:8000` when `NEXT_PUBLIC_API_BASE` is unset.

- `components/ChatWindow.tsx` ("use client"): manages `messages`, `input`, `sessionId`, `streaming` state. `send()` appends a user bubble, appends an empty assistant bubble, then iterates `streamChat`: `session` → stores sessionId for continuation; `citations` → attaches parsed `Citation[]` to current assistant message; `token` → accumulates into last message content; `done` → exits loop; `error` → renders safe error text. SessionId persisted across sends so follow-up messages resolve the prior ticker via backend coreference.

- `components/MessageBubble.tsx`: renders content via `<ReactMarkdown>` with no `rehype-raw` plugin and no `dangerouslySetInnerHTML` anywhere (T-06-01 XSS defense). When an assistant message has citations, renders a `Sources` list as `[N] source_path • report_type • generated_date`. Safe anchor override (`target="_blank" rel="noopener noreferrer"`).

- `lib/types.ts`: `Citation`, `ChatRequest`, `ChatResponse`, `StreamEvent`, `Message` — exact mirrors of `backend/src/schemas.py` field names.

---

## Task Commits (nested trading-chatbot repo)

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Bootstrap scaffold + types + streamChat | `053cb58` | package.json, next.config.mjs, tailwind.config.ts, tsconfig.json, postcss.config.mjs, next-env.d.ts, app/layout.tsx, app/globals.css, lib/types.ts, lib/api.ts, .env.local.example, .gitignore |
| 2 | ChatWindow + MessageBubble + page | `ca86c91` | components/ChatWindow.tsx, components/MessageBubble.tsx, app/page.tsx |

---

## Files Created/Modified

- `trading-chatbot/frontend/package.json` — project manifest; next@14.2.29 + react/react-dom + ai/@ai-sdk/openai/eventsource-parser/react-markdown + TS+Tailwind devdeps
- `trading-chatbot/frontend/next.config.mjs` — minimal Next.js config (no rewrites needed for local dev)
- `trading-chatbot/frontend/tailwind.config.ts` — App Router content glob + theme extensions
- `trading-chatbot/frontend/tsconfig.json` — strict TS, bundler moduleResolution, @/* alias
- `trading-chatbot/frontend/postcss.config.mjs` — tailwindcss + autoprefixer
- `trading-chatbot/frontend/next-env.d.ts` — Next.js type shims
- `trading-chatbot/frontend/app/layout.tsx` — Inter font, dark bg-gray-950, metadata
- `trading-chatbot/frontend/app/globals.css` — Tailwind directives + chat-scroll + prose overrides
- `trading-chatbot/frontend/app/page.tsx` — server component, header bar, renders ChatWindow
- `trading-chatbot/frontend/lib/types.ts` — Citation/ChatRequest/ChatResponse/StreamEvent/Message
- `trading-chatbot/frontend/lib/api.ts` — streamChat async generator, blank-line SSE split
- `trading-chatbot/frontend/components/ChatWindow.tsx` — "use client", all 4+1 event handlers, sessionId continuity
- `trading-chatbot/frontend/components/MessageBubble.tsx` — ReactMarkdown + Sources, XSS-safe
- `trading-chatbot/frontend/.env.local.example` — NEXT_PUBLIC_API_BASE=http://localhost:8000
- `trading-chatbot/.gitignore` — added *.tsbuildinfo

---

## Build / Typecheck

| Check | Outcome |
|-------|---------|
| `npm install` | 270 packages installed (10s) |
| `npm run build` | PASS — compiled successfully; 4/4 static pages generated |
| `npx tsc --noEmit` | PASS — zero errors |
| XSS scan (no rehype-raw / dangerouslySetInnerHTML) | PASS — only in comment text, never in code |

---

## Decisions Made

- **Native fetch + ReadableStream for SSE.** The `ai` and `eventsource-parser` packages are declared in `package.json` (per the locked dep list in 01-CONTEXT.md) but `streamChat` uses the native browser Fetch API with a `ReadableStream` reader and manual `\n\n` splitting. The backend uses a `POST` endpoint for `/chat/stream` (not `GET`) — the native `EventSource` API only supports `GET` — so fetch-based streaming is the correct approach and avoids an extra abstraction layer.

- **ReactMarkdown without rehype-raw (T-06-01 mitigated).** LLM output is rendered via `<ReactMarkdown>` with no `rehype-raw` plugin added. `dangerouslySetInnerHTML` is never used anywhere in the component tree. This prevents XSS via crafted markdown (e.g., `<script>` tags or inline `onclick` attributes) from the LLM response.

- **sessionId in React state (not localStorage).** Phase 1 is a single-user single-session MVP. Persisting sessionId across page reloads is a Phase 2 concern (auth + session sidebar). Keeping it in `useState` avoids unintended session leakage between dev restarts.

- **`updateLastMessage` functional updater.** Streaming tokens accumulate via `setMessages(prev => [...prev.slice(0,-1), updater(prev[prev.length-1])])`. Using the functional form prevents stale closure bugs that would occur if the async generator captured `messages` by reference at call time.

---

## Browser Verification (Human-Verify Pending)

Task 3 is `checkpoint:human-verify`. Per plan execution notes, this gate is recorded here rather than blocking.

**To verify end-to-end:**

1. Start backend: `cd trading-chatbot/backend && uv run uvicorn src.main:app --reload` (with `PINECONE_READ_KEY` + `OPENAI_API_KEY` set in `.env`).
2. Start frontend: `cd trading-chatbot/frontend && npm run dev`.
3. Open http://localhost:3000.
4. Type **"bull case for AAPL"** and observe:
   - [ ] Response streams token-by-token (not all at once)
   - [ ] A "Sources" list renders under the assistant bubble
5. Send **"what about its risks?"** in the same session and confirm:
   - [ ] Response resolves AAPL without restating the ticker (session coreference)
6. Confirm the answer ends with the educational/not-financial-advice disclaimer.

All criteria are Phase 1 success criteria (01-ROADMAP.md 1, 2, 4).

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] postcss.config.mjs added**
- **Found during:** Task 1
- **Issue:** Tailwind CSS requires a PostCSS config to process `@tailwind` directives. The plan listed `tailwind.config.ts` but not `postcss.config.mjs`. Without it, `npm run build` would fail with Tailwind directives unprocessed.
- **Fix:** Added `postcss.config.mjs` with `tailwindcss` + `autoprefixer` plugins (standard Next.js + Tailwind setup).
- **Files modified:** `frontend/postcss.config.mjs` (new)
- **Commit:** `053cb58`

**2. [Rule 2 - Missing Critical Functionality] *.tsbuildinfo added to .gitignore**
- **Found during:** Task 1
- **Issue:** `npm install` + `npx tsc` generated `frontend/tsconfig.tsbuildinfo` (TypeScript incremental build cache). This build artifact was untracked and would pollute the repo.
- **Fix:** Added `*.tsbuildinfo` to `trading-chatbot/.gitignore`.
- **Files modified:** `trading-chatbot/.gitignore`
- **Commit:** `053cb58`

---

## Known Stubs

None. All components are wired to real backend endpoints. The only "pending" item is the browser end-to-end human verification (Task 3 checkpoint — recorded above).

---

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: xss_mitigated | `components/MessageBubble.tsx` | T-06-01 mitigated: ReactMarkdown with no rehype-raw; no dangerouslySetInnerHTML anywhere |
| threat_flag: cors_note | `lib/api.ts` | T-06-02: backend CORS limited to http://localhost:3000 (configured in backend/src/config.py); frontend NEXT_PUBLIC_API_BASE must match |
| threat_flag: citations_safe | `components/MessageBubble.tsx` | T-06-03 mitigated: Sources list renders only citations emitted by the backend from real chunk metadata |

---

## Self-Check: PASSED

Files confirmed on disk:
- trading-chatbot/frontend/package.json: FOUND
- trading-chatbot/frontend/lib/api.ts: FOUND (streamChat present)
- trading-chatbot/frontend/lib/types.ts: FOUND (Citation/source_path/generated_date present)
- trading-chatbot/frontend/components/ChatWindow.tsx: FOUND (session/citations/token/done handled)
- trading-chatbot/frontend/components/MessageBubble.tsx: FOUND (ReactMarkdown + Sources present)
- trading-chatbot/frontend/app/page.tsx: FOUND (ChatWindow rendered)
- trading-chatbot/frontend/.env.local.example: FOUND

Nested repo commits confirmed:
- 053cb58: feat(01-06): Next.js 14 scaffold + streamChat async-generator client
- ca86c91: feat(01-06): ChatWindow + MessageBubble + page — streaming chat UI

Build: PASS (npm run build — 4/4 static pages)
Typecheck: PASS (npx tsc --noEmit — zero errors)

---

*Phase: 01-chatbot-mvp*
*Completed: 2026-06-08*
