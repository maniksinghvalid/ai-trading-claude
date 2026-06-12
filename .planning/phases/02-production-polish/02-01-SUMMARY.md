---
phase: 02-production-polish
plan: "01"
subsystem: backend-nlp
tags: [ticker-extraction, intent-classification, coreference, schema-regression, tdd]
dependency_graph:
  requires:
    - "Phase 1 backend (/chat, /chat/stream, session_store, llm_client)"
    - "Pinecone schema contract (docs/schema-contract.md)"
  provides:
    - "src.ticker_extractor.extract_tickers (KNOWN_TICKERS, regex + LLM fallback)"
    - "src.intent_classifier.classify_intent (Intent literal, fixed-schema LLM)"
    - "routes/chat.py: 3-tier ticker resolution (explicit > extracted > coreference)"
    - "tests/test_schema_contract.py: VERIFY-SCHEMA regression test"
  affects:
    - "routes/chat.py (both post_chat and post_chat_stream)"
    - "All chat endpoint tests (autouse stubs for new imports)"
tech_stack:
  added: []
  patterns:
    - "Rule-based regex first pass + LLM fallback for NLP (no new dependency)"
    - "Module-level re-export of complete() for test monkeypatching"
    - "autouse pytest fixture for offline stubbing of route-level imports"
key_files:
  created:
    - "trading-chatbot/backend/src/ticker_extractor.py"
    - "trading-chatbot/backend/src/intent_classifier.py"
    - "trading-chatbot/backend/tests/test_ticker_extractor.py"
    - "trading-chatbot/backend/tests/test_intent_classifier.py"
    - "trading-chatbot/backend/tests/test_schema_contract.py"
  modified:
    - "trading-chatbot/backend/src/routes/chat.py"
    - "trading-chatbot/backend/tests/test_chat_endpoint.py"
    - "trading-chatbot/backend/tests/test_chat_stream.py"
decisions:
  - "KNOWN_TICKERS allowlist guards 1-char false positives (Intelsat 'I' guard) — add symbols as holdings grow"
  - "LLM fallback fires only when regex yields zero tickers (cost-bounded by T-02-01-02)"
  - "classify_intent degrades to factual + regex tickers on any LLM failure (T-02-01-03)"
  - "3-tier ticker resolution: explicit req.ticker > first extracted > coreference (existing ticker_scope)"
  - "intent result stored in _intent_result local var; no live-quote logic yet (slice 7 consumes it)"
  - "autouse fixture pattern for offline stubs avoids touching each existing test individually"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-09"
  tasks_completed: 3
  files_created: 5
  files_modified: 3
---

# Phase 02 Plan 01: Ticker Extraction + Intent Classification + Schema Regression Summary

**One-liner:** Rule-based regex + LLM fallback ticker resolution with intent classification (factual/trajectory/comparison/action/chitchat) wired into both /chat endpoints, guarded by a VERIFY-SCHEMA regression test.

## What Was Built

### Task 1: Ticker Extractor (TDD — RED then GREEN)
`trading-chatbot/backend/src/ticker_extractor.py` exports:
- `KNOWN_TICKERS: set[str]` — 60-symbol allowlist seeded from large-cap holdings; guards 1-char false positives (e.g. "I" for Intelsat, "A" not in allowlist).
- `extract_tickers(text) -> list[str]` — regex first pass `\$?([A-Z]{1,5}(?:\.[A-Z])?)\b`; single-char candidates accepted only if in `KNOWN_TICKERS`; LLM fallback fires only when regex yields nothing; deduplicates preserving order.
- `complete` re-exported at module level so tests can monkeypatch `src.ticker_extractor.complete`.

14 unit tests in `test_ticker_extractor.py` — all passing offline.

### Task 2: Intent Classifier (TDD — RED then GREEN)
`trading-chatbot/backend/src/intent_classifier.py` exports:
- `Intent` — `Literal["factual", "trajectory", "comparison", "action", "chitchat"]`
- `classify_intent(text) -> dict` — fixed-schema LLM call returns `{intent, tickers}`; on JSON decode failure or out-of-enum intent degrades gracefully to `{"intent": "factual", "tickers": extract_tickers(text)}` (T-02-01-03).
- `complete` re-exported at module level for monkeypatching.

13 unit tests in `test_intent_classifier.py` — all passing offline.

### Task 3: Wire + Schema Regression Test
Modified `routes/chat.py` (both `post_chat` and `post_chat_stream`):
- Calls `extract_tickers(req.message)` and `classify_intent(req.message)` before `retrieve()`.
- **3-tier ticker resolution:** explicit `req.ticker` > first extracted ticker > coreference from `ticker_scope` in history.
- `_intent_result` stored in local var for slice 7 (live-quote gating); no behavior change in this plan.
- Coreference inheritance (`ticker_scope`) preserved as final fallback.

Created `tests/test_schema_contract.py`:
- `test_required_metadata_fields_present` marked `@pytest.mark.live_index`; calls `retrieve("AAPL recent analysis", ticker="AAPL", k=1)` and asserts `ticker`, `report_type`, `generated_at`, `generated_date`, `source_path` are all present and non-empty; fails loudly naming the missing field.
- Auto-skips when `PINECONE_READ_KEY` is unset (conftest auto-skip pattern).

Updated `test_chat_endpoint.py` and `test_chat_stream.py`:
- Added `autouse=True` fixture `stub_extractor_and_classifier` in each file; stubs `src.routes.chat.extract_tickers` and `src.routes.chat.classify_intent` to harmless defaults so all existing tests stay green without network calls.
- Added `test_post_chat_auto_ticker_from_message` (TICK-01 gate: "how is apple doing" -> AAPL into retrieve) and `test_post_chat_explicit_ticker_wins_over_extraction` in `test_chat_endpoint.py`.

## Verification

```
cd trading-chatbot/backend && uv run pytest
77 passed, 6 skipped, 1 warning
```

The 6 skips are: 5 existing `live_index` Pinecone smoke tests + 1 new `test_schema_contract.py` (all skip cleanly without `PINECONE_READ_KEY`). No failures.

## Commits (in nested `trading-chatbot/` repo)

| Hash | Message |
|------|---------|
| 44ec83d | test(02-01): add failing tests for ticker_extractor (RED) |
| 33f6bd7 | feat(02-01): implement ticker_extractor with regex + LLM fallback (GREEN) |
| 2849555 | test(02-01): add failing tests for intent_classifier (RED) |
| 79f62f6 | feat(02-01): implement intent_classifier with fixed-schema LLM call (GREEN) |
| ac04533 | feat(02-01): wire extract_tickers+classify_intent into /chat + schema regression test |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all functionality is real code (no hardcoded placeholders or TODO stubs). The intent result (`_intent_result`) is intentionally stored but not yet consumed; this is documented in the plan and will be picked up by slice 7 (plan 02-02).

## Threat Surface Scan

No new network endpoints or auth paths introduced. The two new modules (`ticker_extractor`, `intent_classifier`) make LLM calls using the existing `llm_client.complete()` channel (same threat surface as the existing `/chat` flow). T-02-01-01, T-02-01-02, T-02-01-03 all mitigated as specified in the plan threat register.

## Self-Check: PASSED

Files verified present:
- trading-chatbot/backend/src/ticker_extractor.py: EXISTS
- trading-chatbot/backend/src/intent_classifier.py: EXISTS
- trading-chatbot/backend/tests/test_ticker_extractor.py: EXISTS
- trading-chatbot/backend/tests/test_intent_classifier.py: EXISTS
- trading-chatbot/backend/tests/test_schema_contract.py: EXISTS

Commits verified: 44ec83d, 33f6bd7, 2849555, 79f62f6, ac04533 all present in trading-chatbot git log.
