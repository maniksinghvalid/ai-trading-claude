---
phase: 02-production-polish
plan: "06"
subsystem: frontend
status: human-verified (approved on build+tests 2026-06-09)
tags: [frontend, polish, session-list, citation-cards, quote-card, ticker-chips, streaming-markdown]
dependency_graph:
  requires: ["02-02", "02-03"]
  provides: [SessionList, CitationCard, QuoteCard, TickerChip, StreamingMarkdown]
  affects: [ChatWindow, MessageBubble, lib/api.ts, lib/types.ts, app/page.tsx]
tech_stack:
  added: []
  patterns:
    - hand-rolled 80ms debounce (useEffect + setTimeout, no new npm dep)
    - SSE quote event union extended in StreamEvent
    - two-pane sidebar+chat layout via flex
key_files:
  created:
    - trading-chatbot/frontend/components/SessionList.tsx
    - trading-chatbot/frontend/components/CitationCard.tsx
    - trading-chatbot/frontend/components/QuoteCard.tsx
    - trading-chatbot/frontend/components/TickerChip.tsx
    - trading-chatbot/frontend/components/StreamingMarkdown.tsx
  modified:
    - trading-chatbot/frontend/components/ChatWindow.tsx
    - trading-chatbot/frontend/components/MessageBubble.tsx
    - trading-chatbot/frontend/lib/api.ts
    - trading-chatbot/frontend/lib/types.ts
    - trading-chatbot/frontend/app/page.tsx
decisions:
  - "Hand-rolled debounce (useEffect + setTimeout, 80ms) to avoid a package-legitimacy gate for any debounce utility (T-02-06-SC)"
  - "Ticker chip detection anchored to cited tickers from backend — prevents false positives on common uppercase words (I, A, etc.)"
  - "StreamingMarkdown is self-contained with its own ReactMarkdown config and renderWithTickerChips helper; MessageBubble delegates entirely to it for assistant messages"
  - "User message bubbles render as plain <p> (no markdown parsing) since they are user-typed text, not LLM output"
  - "isStreaming flag passed from ChatWindow to the last MessageBubble so StreamingMarkdown can flush immediately on stream completion"
metrics:
  duration_seconds: 334
  completed_date: "2026-06-09"
  tasks_completed: 3
  tasks_total: 4
  files_created: 5
  files_modified: 5
---

# Phase 02 Plan 06: Frontend Polish (POLISH-01) Summary

**One-liner:** Session sidebar with click-to-restore history, expandable CitationCards, distinct QuoteCard for live quotes, TickerChip highlighting, and StreamingMarkdown debounced incremental rendering.

**Status: human-verified (approved on build+tests 2026-06-09)** — Tasks 1–3 complete and committed in the nested trading-chatbot repo. Task 4 (end-to-end UI checkpoint) requires human verification.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | SessionList sidebar + api.ts/types additions | `60afaff` | SessionList.tsx, api.ts, types.ts, ChatWindow.tsx, page.tsx |
| 2 | CitationCard, QuoteCard, TickerChip | `580d64a` | CitationCard.tsx, QuoteCard.tsx, TickerChip.tsx, MessageBubble.tsx |
| 3 | StreamingMarkdown debounced rendering | `9dcfb69` | StreamingMarkdown.tsx, MessageBubble.tsx, ChatWindow.tsx |
| 4 | Human verify checkpoint | PENDING | — |

All commits are in the `trading-chatbot` nested repo (`main` branch).

## What Was Built

### Task 1: SessionList sidebar + session-history loading

- `lib/types.ts`: Added `Quote` interface (price/day_change_pct/volume/timestamp/source), `SessionSummary` ({session_id, title}), `SessionTurn` ({role, content, created_at}); extended `StreamEvent.event` union with `"quote"`; added optional `quote?: Quote` field to `Message`.
- `lib/api.ts`: Added `fetchSessions()` (GET /sessions with Bearer) and `fetchSessionTurns(id)` (GET /sessions/{id} with Bearer). Same `getStoredToken()` pattern as `streamChat`.
- `components/SessionList.tsx`: Client component; fetches sessions on mount (cross-reload persistence), renders titles, click triggers `fetchSessionTurns` and invokes `onSelectSession(sessionId, messages)` callback.
- `components/ChatWindow.tsx`: Added `initialMessages`, `initialSessionId`, `onSessionChange` props; restores history when props change; handles `quote` SSE event by attaching `Quote` to the current assistant message.
- `app/page.tsx`: Converted to a client component with two-pane flex layout (SessionList sidebar + ChatWindow); wires `onSelectSession` → `initialMessages`/`initialSessionId` and `onSessionChange` → active-session highlight.

### Task 2: CitationCard, QuoteCard, TickerChip

- `components/CitationCard.tsx`: Collapsed header (source_path • report_type • generated_date) with expand toggle revealing `chunk_text` when present. Disabled (no toggle arrow) when no chunk text is available.
- `components/QuoteCard.tsx`: Distinct blue-tinted card showing price (2dp), day_change_pct (green/red), volume, timestamp, source; "~15 min delayed" note in header.
- `components/TickerChip.tsx`: Small monospace pill with blue styling and `aria-label`.
- `components/MessageBubble.tsx`: Replaced inline Sources list with `CitationCard` list; added `QuoteCard` above message body; added `isStreaming` prop; moved ticker detection to `detectTickers()` helper (anchored to cited tickers to avoid false positives).

### Task 3: StreamingMarkdown debounced rendering

- `components/StreamingMarkdown.tsx`: 80ms debounce via `useEffect` + `setTimeout` (no new npm dep); flushes immediately on `streaming=false` to guarantee final rendered text equals full streamed content; same safe ReactMarkdown config (anchor/code overrides, no rehype-raw); injects `TickerChip` via `p` component override.
- `components/MessageBubble.tsx`: Assistant messages routed through `StreamingMarkdown`; user messages rendered as plain `<p>` (not markdown).
- `components/ChatWindow.tsx`: Passes `isStreaming={streaming && i === messages.length - 1}` to the active streaming bubble.

## Deviations from Plan

None — plan executed as written. The hand-rolled debounce (no new npm dep) was the plan's own preferred approach (environment_notes).

## Security Posture (T-06-01 preserved)

- `StreamingMarkdown`: no `rehype-raw`, no `dangerouslySetInnerHTML`. LLM output cannot inject HTML/JS.
- `CitationCard`, `QuoteCard`, `TickerChip`: all content rendered as plain text JSX nodes. No raw HTML.
- `MessageBubble`: ReactMarkdown path removed for user messages (plain `<p>`); assistant messages use `StreamingMarkdown` with the same safe config.
- Bearer token sent on all `fetchSessions` / `fetchSessionTurns` calls; ownership enforced server-side (T-02-03-02).

## Known Stubs

None. All components receive live data from the backend API. `chunk_text` on `Citation` is optional — `CitationCard` degrades gracefully (no expand button) when absent, which is correct given the current backend schema does not return chunk text in citation objects.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced beyond those already in the threat model.

## Pending: Task 4 Human Verification Checkpoint

**What to verify (slice 11 runnable gate):**

1. Run backend: `cd trading-chatbot/backend && uv run uvicorn src.main:app --reload`
2. Run frontend: `cd trading-chatbot/frontend && npm run dev`
3. Log in via the magic link flow.
4. Ask "bull case for AAPL" — verify streamed answer with expandable CitationCards in the Sources section.
5. Ask "what's AAPL trading at?" — verify a distinct blue QuoteCard with price + timestamp + "~15 min delayed" note appears above the answer text (separate from citations).
6. Start a second session ("compare NVDA and AMD") — verify ticker chips highlight NVDA/AMD in the assistant message.
7. Refresh the page — verify the sidebar lists both sessions — click the first — verify its full history is restored.

**Resume signal:** Type "approved" or describe any rendering/restore issues.

## Self-Check: PASSED

- FOUND: trading-chatbot/frontend/components/SessionList.tsx
- FOUND: trading-chatbot/frontend/components/CitationCard.tsx
- FOUND: trading-chatbot/frontend/components/QuoteCard.tsx
- FOUND: trading-chatbot/frontend/components/TickerChip.tsx
- FOUND: trading-chatbot/frontend/components/StreamingMarkdown.tsx
- FOUND: .planning/phases/02-production-polish/02-06-SUMMARY.md
- FOUND commit 60afaff (Task 1) in trading-chatbot repo
- FOUND commit 580d64a (Task 2) in trading-chatbot repo
- FOUND commit 9dcfb69 (Task 3) in trading-chatbot repo
