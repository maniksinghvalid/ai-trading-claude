---
phase: 01-chatbot-mvp
plan: "01"
subsystem: trading-chatbot/bootstrap
tags: [pinecone, schema-contract, repo-bootstrap, consumer]
dependency_graph:
  requires: []
  provides:
    - trading-chatbot repo skeleton (backend/, frontend/, docs/, plan/, scripts/)
    - docs/schema-contract.md (read-only producer/consumer metadata contract)
    - scripts/smoke_index.py (live-index smoke gate)
    - .env.example (env var template)
  affects:
    - All downstream plans (01-02 through 01-06) — repo skeleton is the prerequisite
tech_stack:
  added:
    - pinecone>=5 (smoke dependency; full backend dep added in 01-02)
  patterns:
    - Consumer-only Pinecone read path (no write access)
    - Reader-role API key pattern (PINECONE_READ_KEY)
key_files:
  created:
    - trading-chatbot/.gitignore
    - trading-chatbot/.env.example
    - trading-chatbot/README.md
    - trading-chatbot/docs/architecture.md
    - trading-chatbot/docs/schema-contract.md
    - trading-chatbot/scripts/smoke_index.py
    - trading-chatbot/plan/trading-chatbot.md (mirrored from outer repo)
    - trading-chatbot/backend/.gitkeep
    - trading-chatbot/frontend/.gitkeep
    - trading-chatbot/plan/.gitkeep
  modified: []
decisions:
  - "Nested git repo: trading-chatbot/ initialized as its own repo inside ai-trading-claude; outer repo does not git-track it (no gitlink)"
  - "risk_score INVERTED convention documented explicitly in schema-contract.md (higher = safer)"
  - "smoke_index.py exits 0 on missing key — safe to run in CI without credentials"
  - "plan/trading-chatbot.md mirrored into new repo per repository layout spec"
metrics:
  duration: "~3 minutes"
  completed_date: "2026-06-08"
  tasks_completed: 3
  files_created: 10
---

# Phase 1 Plan 1: Repo Bootstrap + Schema Contract Summary

**One-liner:** Initialized `trading-chatbot/` as a standalone consumer-only repo with directory skeleton, `.env.example`, read-only schema contract doc mirroring the upstream Pinecone field table, and a smoke script that gracefully skips when no key is set.

---

## Tasks Completed

| Task | Name | Nested Repo Commit | Key Files |
|------|------|--------------------|-----------|
| 1 | Initialize repo skeleton + .env.example + gitignore | `4990439` | `.gitignore`, `.env.example`, `README.md`, `docs/architecture.md`, `backend/.gitkeep`, `frontend/.gitkeep`, `plan/.gitkeep` |
| 2 | Write docs/schema-contract.md | `4c273a3` | `docs/schema-contract.md` |
| 3 | Implement smoke_index.py (live-index smoke) | `9cfc099` | `scripts/smoke_index.py` |
| — | Mirror plan/trading-chatbot.md into new repo | `2de947f` | `plan/trading-chatbot.md` |

---

## Smoke Test Outcome

**No-key path (confirmed):** Running `python3 trading-chatbot/scripts/smoke_index.py` without
`PINECONE_READ_KEY` prints:
```
PINECONE_READ_KEY not set — skipping live-index smoke (exit 0).
To run: export PINECONE_READ_KEY=<reader-key> && python scripts/smoke_index.py
```
Exit code: 0. This satisfies the "no key" acceptance criterion.

**Live path (human verification pending):** The `pinecone` package is not installed in this
execution environment, so a live run against the `trade-reports` index could not be completed
here. The outer repo's `.env` contains `PINECONE_API_KEY`. To complete the live gate:

```bash
pip install "pinecone>=5"
PINECONE_READ_KEY=$(grep PINECONE_API_KEY /path/to/.env | cut -d= -f2) \
  python3 trading-chatbot/scripts/smoke_index.py
```

Expected output: namespace `trade` listed with a vector count >= 0 (0 is acceptable for
slice 0). No tracebacks. Exit code 0.

---

## Deviations from Plan

**1. [Rule 2 - Missing functionality] Mirrored plan/trading-chatbot.md into new repo**
- **Found during:** Post-task review of repository layout spec
- **Issue:** The repository layout in `plan/trading-chatbot.md` shows `plan/trading-chatbot.md` as a file in the new repo ("this file, mirrored")
- **Fix:** Copied `plan/trading-chatbot.md` from the outer repo to `trading-chatbot/plan/trading-chatbot.md`
- **Files modified:** `trading-chatbot/plan/trading-chatbot.md`
- **Commit:** `2de947f`

Otherwise: plan executed exactly as written.

---

## Known Stubs

None — this plan produces only documentation and a utility script, with no UI or data-source components.

---

## Threat Flags

No new network endpoints, auth paths, or schema changes introduced. The `.gitignore` correctly excludes `.env` (T-01-01 mitigated). The smoke script uses a Reader-role-only key path (T-01-02 mitigated). The `pinecone>=5` package requirement is noted per T-01-SC.

---

## Self-Check: PASSED

Files confirmed on disk:
- trading-chatbot/.gitignore: FOUND
- trading-chatbot/.env.example: FOUND
- trading-chatbot/README.md: FOUND
- trading-chatbot/docs/architecture.md: FOUND
- trading-chatbot/docs/schema-contract.md: FOUND
- trading-chatbot/scripts/smoke_index.py: FOUND
- trading-chatbot/plan/trading-chatbot.md: FOUND

Nested repo commits confirmed:
- 4990439: feat(01-01): bootstrap trading-chatbot repo skeleton
- 4c273a3: docs(01-01): add schema-contract.md from producer read-only contract
- 9cfc099: feat(01-01): add live-index smoke script (smoke_index.py)
- 2de947f: docs(01-01): mirror plan/trading-chatbot.md into new repo per layout spec
