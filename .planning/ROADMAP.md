# Roadmap: Trading Chatbot

## Overview

A cited, memory-grounded trading chatbot — a pure consumer of the `trade-reports` Pinecone
index. Educational/research only; not financial advice.

## Milestones

- ✅ **v1.0 — Chatbot MVP + Production Polish** (Phases 1–2, 16 plans) — **SHIPPED 2026-06-11**.
  Grounded RAG chat with citations, multi-turn coreference, SSE streaming, Next.js UI; plus
  ticker/intent extraction, live market quotes, magic-link auth + per-user isolation, Postgres,
  rate limiting, polished frontend, and containerized deploy + CI schema gate.
  - Detail: [milestones/v1.0-ROADMAP.md](milestones/v1.0-ROADMAP.md)
  - Requirements: [milestones/v1.0-REQUIREMENTS.md](milestones/v1.0-REQUIREMENTS.md)
  - Audit: [v1.0-MILESTONE-AUDIT.md](v1.0-MILESTONE-AUDIT.md) (passed, 17/17)

## Next Milestone

_Not yet defined. Run `/gsd-new-milestone` to scope v1.1 (e.g. admin-route hygiene, real-time
market data, CHAT-ingest opt-in)._

## Backlog

- Wire `admin.py` `_require_admin` via `Depends` (dead-code hygiene; carried from v1.0 audit).
