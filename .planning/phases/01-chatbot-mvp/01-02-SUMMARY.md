---
phase: 01-chatbot-mvp
plan: "02"
subsystem: backend/pinecone
tags: [fastapi, pinecone, pydantic-settings, uvicorn, pytest, retrieval, rag]

dependency_graph:
  requires:
    - phase: 01-01
      provides: trading-chatbot repo skeleton, docs/schema-contract.md, .env.example
  provides:
    - backend/pyproject.toml with locked dependency set + uv.lock
    - backend/src/config.py: Pydantic Settings with all Phase 1 env fields
    - backend/src/main.py: FastAPI app with CORSMiddleware + health router
    - backend/src/pinecone_client.py: retrieve/latest/timeline/_normalize primitives
    - backend/src/routes/health.py: /healthz and /readyz endpoints
    - backend/tests/conftest.py: live_index marker + auto-skip without key
    - backend/tests/test_pinecone_client.py: 8 unit + 5 live-index smoke tests
  affects:
    - 01-03 (RAG chat endpoint uses pinecone_client.retrieve)
    - 01-04 (conversation store uses config.database_url)
    - 01-05 (SSE streaming endpoint builds on main.py + config)
    - 01-06 (frontend talks to /healthz and /readyz to verify backend is up)

tech-stack:
  added:
    - fastapi>=0.115 (HTTP framework)
    - uvicorn[standard]>=0.32 (ASGI server)
    - pinecone>=5 (Pinecone SDK, integrated-inference query)
    - openai>=1.0 (LLM client — field present in config, client added in 01-03)
    - pydantic>=2.9 + pydantic-settings>=2.6 (settings + validation)
    - sqlmodel>=0.0.22 (conversation store ORM — wired in 01-04)
    - psycopg[binary]>=3.2 (Postgres driver — present for Phase 2 migration)
    - sse-starlette>=2.1 (SSE streaming — wired in 01-05)
    - httpx>=0.27 (async HTTP client)
    - pytest>=8, pytest-asyncio>=0.24, respx>=0.21 (dev/test)
  patterns:
    - Pydantic BaseSettings for all runtime config; single `settings` singleton
    - read-only Pinecone client: ID-prefix list/fetch for latest/timeline (avoids unreliable metadata filters)
    - schema_version validated on every _normalize() call; UnknownSchemaVersionError on unknown majors
    - live_index pytest marker + conftest auto-skip pattern for credential-gated tests
    - /readyz 503 with generic body — never leaks key or stack trace (T-02-01)

key-files:
  created:
    - trading-chatbot/backend/pyproject.toml
    - trading-chatbot/backend/.python-version
    - trading-chatbot/backend/uv.lock
    - trading-chatbot/backend/src/__init__.py
    - trading-chatbot/backend/src/config.py
    - trading-chatbot/backend/src/main.py
    - trading-chatbot/backend/src/pinecone_client.py
    - trading-chatbot/backend/src/routes/__init__.py
    - trading-chatbot/backend/src/routes/health.py
    - trading-chatbot/backend/tests/__init__.py
    - trading-chatbot/backend/tests/conftest.py
    - trading-chatbot/backend/tests/test_pinecone_client.py
  modified: []

key-decisions:
  - "openai_model default set to gpt-4o (current flagship); easily overridden via OPENAI_MODEL env var"
  - "retrieve() applies server-side metadata filter as best-effort AND always post-filters returned matches — dual-gate per retrieval gotcha"
  - "dependency-groups.dev (PEP 735) used instead of deprecated tool.uv.dev-dependencies"
  - "sentinel pattern (object()) in retrieve() to distinguish empty list from absent attribute — prevents falsy-list bug"

patterns-established:
  - "All runtime settings via config.py Settings singleton — never import env vars directly"
  - "Pinecone latest/timeline: ID-prefix list first, then batch fetch — never rely on metadata $eq/$in filters"
  - "Live-index tests use @pytest.mark.live_index; conftest auto-skips when PINECONE_READ_KEY unset"
  - "Health check error handling: log internally, return generic 503 body — no secrets in responses"

requirements-completed: [RAG-01, RAG-02]

duration: ~25min
completed: 2026-06-08
---

# Phase 1 Plan 2: Backend Skeleton + Pinecone Retrieval Client Summary

**FastAPI backend skeleton with Pydantic settings, read-only Pinecone retrieval client (retrieve/latest/timeline/_normalize), /healthz + /readyz health endpoints, and a pytest suite (8 unit + 5 live-index smokes) — all in the nested trading-chatbot repo.**

---

## Performance

- **Duration:** ~25 min
- **Started:** 2026-06-08T00:00:00Z
- **Completed:** 2026-06-08T00:25:00Z
- **Tasks:** 3
- **Files modified:** 12 (11 created + 1 pyproject.toml updated mid-task)

---

## Accomplishments

- Complete backend project scaffold: `pyproject.toml` with the full locked dependency set, `.python-version=3.12`, `uv.lock` for reproducibility.
- `config.py` binds all runtime env vars via Pydantic `Settings`; `openai_model` defaults to `gpt-4o` (current OpenAI flagship).
- `pinecone_client.py` implements all three retrieval primitives using ID-prefix list/fetch for `latest`/`timeline` (avoiding unreliable metadata filters per the retrieval gotcha); `schema_version` validated on every read; unknown majors raise `UnknownSchemaVersionError`.
- `/healthz` (fast liveness) and `/readyz` (Pinecone connection gate; 503 with generic body on failure — T-02-01 mitigated).
- pytest runs green: 8 unit tests pass, 5 live-index smokes skip cleanly without `PINECONE_READ_KEY`.

---

## Task Commits (nested trading-chatbot repo)

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Scaffold — pyproject, config, main, health routes | `9bef374` | pyproject.toml, .python-version, config.py, main.py, routes/health.py |
| 2 | Pinecone retrieval client | `5653abc` | pinecone_client.py |
| 3 | Tests + conftest + bug fix + pyproject cleanup | `30e9524` | tests/__init__.py, conftest.py, test_pinecone_client.py, uv.lock, pinecone_client.py (fix), pyproject.toml (fix) |

---

## Files Created/Modified

- `trading-chatbot/backend/pyproject.toml` — uv-managed project; locked dep set; dependency-groups.dev
- `trading-chatbot/backend/.python-version` — pins 3.12
- `trading-chatbot/backend/uv.lock` — reproducible lock file
- `trading-chatbot/backend/src/config.py` — Pydantic Settings singleton; all Phase 1 env fields
- `trading-chatbot/backend/src/main.py` — FastAPI app + CORSMiddleware + health router
- `trading-chatbot/backend/src/pinecone_client.py` — retrieve/latest/timeline/_normalize + schema validation
- `trading-chatbot/backend/src/routes/health.py` — /healthz and /readyz (503 guard T-02-01)
- `trading-chatbot/backend/tests/conftest.py` — live_index marker + auto-skip fixture
- `trading-chatbot/backend/tests/test_pinecone_client.py` — unit + live-index smoke tests

---

## Decisions Made

- `openai_model` default is `gpt-4o` (current OpenAI flagship model, confirmed at implementation time). Easily overridden via `OPENAI_MODEL` env var.
- Used `dependency-groups.dev` (PEP 735) instead of the deprecated `[tool.uv].dev-dependencies` key — uv emits a deprecation warning on the old form.
- `retrieve()` uses a dual-filter approach: applies server-side Pinecone metadata filter as best-effort, then always post-filters returned matches against ticker/report_type as the authoritative gate.

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed falsy-list AttributeError in retrieve()**
- **Found during:** Task 3 (running pytest — test_postfilter_empty_results)
- **Issue:** `getattr(results, "matches", None) or results.get("matches", [])` falls through to `results.get()` when `matches=[]` (empty list is falsy). FakeResult object has no `.get()` — raises `AttributeError`.
- **Fix:** Replaced with sentinel-based detection: `_sentinel = object(); _attr = getattr(results, "matches", _sentinel); if _attr is not _sentinel: matches = _attr`. Correctly handles empty list, missing attribute, and dict responses.
- **Files modified:** `trading-chatbot/backend/src/pinecone_client.py`
- **Verification:** `test_postfilter_empty_results` passes; full suite green.
- **Committed in:** `30e9524`

**2. [Rule 1 - Bug] Migrated deprecated tool.uv.dev-dependencies**
- **Found during:** Task 3 (pytest run output)
- **Issue:** uv emits `warning: The tool.uv.dev-dependencies field ... is deprecated` on every `uv run pytest` invocation.
- **Fix:** Moved dev deps to `[dependency-groups] dev = [...]` per PEP 735 and current uv docs.
- **Files modified:** `trading-chatbot/backend/pyproject.toml`
- **Verification:** No deprecation warnings in subsequent `uv run pytest` run.
- **Committed in:** `30e9524`

---

**Total deviations:** 2 auto-fixed (both Rule 1 — bugs caught by tests/warnings)
**Impact on plan:** Both fixes necessary for correctness and clean tooling output. No scope creep.

---

## Issues Encountered

- `uv pip install -e ".[dev]"` doesn't install `[tool.uv].dev-dependencies` (uv's own field, not a PEP 517 extra). Dev deps were installed separately with `uv pip install pytest pytest-asyncio respx`. This was resolved by migrating to `dependency-groups.dev` which `uv sync --dev` handles correctly.

---

## Known Stubs

None — this plan produces backend infrastructure only. No UI components or data sources with placeholder values.

---

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: info_disclosure | `src/routes/health.py` | /readyz catches all Pinecone exceptions and returns generic 503 — key and stack trace never leak (T-02-01 mitigated) |
| threat_flag: schema_tampering | `src/pinecone_client.py` | schema_version validated in _normalize; UnknownSchemaVersionError on unknown majors (T-02-02 mitigated) |

No new unmitigated threat surfaces introduced.

---

## User Setup Required

To run live-index tests or start the server:

1. Copy `.env.example` to `trading-chatbot/backend/.env`
2. Set `PINECONE_READ_KEY=<your-reader-role-key>` (see `docs/schema-contract.md` for how to create one)
3. Set `OPENAI_API_KEY=<your-key>` (needed by slice 2 — LLM client)
4. Run: `cd trading-chatbot/backend && uv run pytest` (live tests will now execute)
5. Start server: `uv run uvicorn src.main:app --reload`
6. Verify: `curl http://localhost:8000/healthz` → `{"status":"ok"}` and `curl http://localhost:8000/readyz` → `{"status":"ok","vector_count":<N>}`

---

## Next Phase Readiness

- `pinecone_client.retrieve()` is ready for slice 2 (RAG chat endpoint — plan 01-03)
- `config.py` has `openai_model` field; `openai_api_key` field ready for LLM client wiring
- `main.py` health router confirms FastAPI app structure is valid; chat router added in 01-03
- Live-index tests will exercise the real index once `PINECONE_READ_KEY` is configured

---

## Self-Check: PASSED

Files confirmed on disk:
- trading-chatbot/backend/pyproject.toml: FOUND
- trading-chatbot/backend/.python-version: FOUND
- trading-chatbot/backend/uv.lock: FOUND
- trading-chatbot/backend/src/config.py: FOUND
- trading-chatbot/backend/src/main.py: FOUND
- trading-chatbot/backend/src/pinecone_client.py: FOUND
- trading-chatbot/backend/src/routes/health.py: FOUND
- trading-chatbot/backend/tests/conftest.py: FOUND
- trading-chatbot/backend/tests/test_pinecone_client.py: FOUND

Nested repo commits confirmed:
- 9bef374: feat(01-02): backend skeleton — pyproject, config, main app, health routes
- 5653abc: feat(01-02): Pinecone retrieval client — retrieve/latest/timeline/_normalize
- 30e9524: feat(01-02): tests, conftest, uv.lock, bug fix in retrieve() + pyproject cleanup

pytest: 8 passed, 5 skipped (live_index tests skip without PINECONE_READ_KEY) — suite is green.

---

*Phase: 01-chatbot-mvp*
*Completed: 2026-06-08*
