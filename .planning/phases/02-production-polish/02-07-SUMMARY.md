---
phase: 02-production-polish
plan: "07"
subsystem: deployment
status: PENDING_HUMAN_CHECKPOINT
tags: [docker, ci, deployment, containerization, verify-schema]
dependency_graph:
  requires: [02-01, 02-04, 02-05, 02-06]
  provides: [DEPLOY-01, VERIFY-SCHEMA]
  affects: [trading-chatbot/backend/Dockerfile, trading-chatbot/frontend/Dockerfile, trading-chatbot/docker-compose.production.yml, trading-chatbot/.github/workflows/ci.yml]
tech_stack:
  added:
    - Docker multi-stage builds (uv builder + python:3.12-slim-bookworm runtime)
    - Next.js Dockerfile (node:20-alpine builder + runtime)
    - GitHub Actions CI (astral-sh/setup-uv@v5, actions/setup-node@v4)
    - Fly.io + Vercel deployment targets (documented)
  patterns:
    - Multi-stage Docker build for minimal runtime image size
    - All secrets via platform env vars — never in Dockerfiles or compose
    - PINECONE_READ_KEY wired to CI env: block (not interpolated into run: shell) — no injection surface
    - conftest.py auto-skip pattern means CI stays green without credentials (VERIFY-SCHEMA skips to 's', not 'F')
key_files:
  created:
    - trading-chatbot/backend/Dockerfile
    - trading-chatbot/backend/.dockerignore
    - trading-chatbot/frontend/Dockerfile
    - trading-chatbot/frontend/.dockerignore
    - trading-chatbot/docker-compose.production.yml
    - trading-chatbot/.github/workflows/ci.yml
    - trading-chatbot/docs/deployment.md
  modified: []
decisions:
  - "Backend Dockerfile: ghcr.io/astral-sh/uv:0.6-python3.12-bookworm-slim builder -> python:3.12-slim-bookworm runtime; CMD uses sh -c to allow PORT env expansion"
  - "Frontend Dockerfile: node:20-alpine builder + runtime; NEXT_PUBLIC_API_BASE passed as ARG at build time (no standalone output configured in next.config.mjs)"
  - "Production compose: POSTGRES_PASSWORD injected via env (not hardcoded); db port NOT exposed publicly; backend healthcheck gates frontend startup"
  - "CI secret handling: PINECONE_READ_KEY assigned to env: block, never interpolated into run: command — safe against injection (security hook verified)"
  - "DATABASE_URL omitted from CI env so Postgres integration tests auto-skip (same pattern as local dev)"
metrics:
  duration: "~3 minutes (auto tasks only; human deploy checkpoint PENDING)"
  completed_date: "2026-06-09"
  tasks_completed: 3
  tasks_pending: 1
  files_created: 7
---

# Phase 2 Plan 07: Containerize + Deploy + CI Schema Gate Summary

**One-liner:** Multi-stage Dockerfiles for uv backend and Next.js frontend, production compose with all secrets via env, CI wiring pytest VERIFY-SCHEMA test with PINECONE_READ_KEY secret, and full deployment docs — awaiting human-run platform deploy + secret configuration.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Backend + frontend Dockerfiles + production compose | `21ca509` | backend/Dockerfile, frontend/Dockerfile, docker-compose.production.yml, backend/.dockerignore, frontend/.dockerignore |
| 2 | CI workflow running pytest + VERIFY-SCHEMA + frontend build/lint | `be31500` | .github/workflows/ci.yml |
| 3 | docs/deployment.md — one-command deploy per service | `881112c` | docs/deployment.md |

## Checkpoint PENDING

**Task:** Human-run deploy + platform secret configuration

**Status:** AWAITING HUMAN ACTION

The deployment artifacts are ready (Dockerfiles, CI, docs). The following cannot be automated — the user must perform these steps:

1. Authenticate backend platform CLI (`fly auth login` or Railway login) and frontend platform (`vercel login`)
2. Set platform secrets (PINECONE_READ_KEY, OPENAI_API_KEY, JWT_SECRET, RESEND_API_KEY, DATABASE_URL/managed Postgres, NEXT_PUBLIC_API_BASE, CORS_ORIGINS) — never in the repo
3. Deploy backend then frontend (one command each — see `docs/deployment.md`)
4. Visit the public frontend URL, log in via magic link, send "bull case for AAPL", confirm a streamed cited response end-to-end through the deployed stack

**Resume signal:** Paste the public frontend URL and confirm chat worked end-to-end (or describe the failure).

## Artifact Verification

### Task 1 — Dockerfiles + compose

- `backend/Dockerfile`: multi-stage (uv builder → python:3.12-slim-bookworm runtime); CMD runs `uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}`
- `frontend/Dockerfile`: node:20-alpine builder (`npm ci && npm run build`) → runtime (`npm run start`); `NEXT_PUBLIC_API_BASE` as ARG + ENV
- `docker-compose.production.yml`: YAML validated (`python -c "yaml.safe_load(...)"` → YAML_VALID); no hardcoded secrets; all injected via env vars; db port not exposed publicly
- `.dockerignore` files: exclude .venv, .env, *.db, __pycache__, node_modules, .next, tests

### Task 2 — CI

- CI YAML validated: `CI_YAML_VALID`
- Triggers: `push` + `pull_request` on all branches
- Backend job: uv sync + `uv run pytest -v`; `PINECONE_READ_KEY: ${{ secrets.PINECONE_READ_KEY }}` in `env:` block (not in `run:` shell — no injection surface)
- Frontend job: `npm ci` + `npm run build` + `npm run lint`
- VERIFY-SCHEMA wired: when PINECONE_READ_KEY secret is present, `test_schema_contract.py` executes live assertions; when absent, auto-skips to 's' via conftest.py

### Task 3 — Deployment docs

- `docs/deployment.md` verified: file exists, contains "deploy" keyword (DOCS_OK)
- Covers: prerequisites, secrets table, Fly.io backend + Vercel frontend one-command deploy, self-hosted Docker Compose path, HTTPS-only note, post-deploy smoke checklist, rollback steps, .env.example template

## Deviations from Plan

None — plan executed exactly as written, with one security review applied:

**Security review (Task 2):** Verified that `PINECONE_READ_KEY` is assigned to the `env:` block rather than interpolated into a `run:` shell command. This is the safe pattern per GitHub Actions injection guidance — the secret value becomes an OS env variable consumed by pytest, never shell-expanded. No other `${{ github.event.* }}` expressions appear in any `run:` command.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced. Mitigations applied:

| Threat | Disposition | Evidence |
|--------|-------------|---------|
| T-02-07-01: Secrets in image/repo | Mitigated | No secrets in Dockerfiles; .dockerignore excludes .env/*.db; compose uses ${VAR} placeholders only |
| T-02-07-02: Upstream schema drift | Mitigated | VERIFY-SCHEMA test wired in CI with PINECONE_READ_KEY; fails loudly on drift |
| T-02-07-03: MITM / plain HTTP | Mitigated | Fly.io terminates TLS; deployment.md documents HTTPS-only and nginx HTTP→HTTPS redirect |
| T-02-07-SC: Base image tampering | Accepted | Official images used: ghcr.io/astral-sh/uv, python:3.12-slim-bookworm, node:20-alpine, postgres:16-alpine |

## Known Stubs

None — this plan creates infrastructure files (Dockerfiles, CI, docs), not UI components. No placeholder data flows to rendering.

## Self-Check: PASSED

All created files exist on disk; all task commits found in git log.

| Item | Status |
|------|--------|
| backend/Dockerfile | FOUND |
| backend/.dockerignore | FOUND |
| frontend/Dockerfile | FOUND |
| frontend/.dockerignore | FOUND |
| docker-compose.production.yml | FOUND |
| .github/workflows/ci.yml | FOUND |
| docs/deployment.md | FOUND |
| Commit 21ca509 (Task 1) | FOUND |
| Commit be31500 (Task 2) | FOUND |
| Commit 881112c (Task 3) | FOUND |
