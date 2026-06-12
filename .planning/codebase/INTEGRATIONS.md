# External Integrations

**Analysis Date:** 2026-06-08

## APIs & External Services

**Market Data & Research:**
- **WebSearch** (Claude Code MCP tool)
  - What it's used for: Gather current stock prices, news, analyst ratings, earnings data, sec filings, company financials, technical indicators
  - Invoked by: All analysis skills (`trade-analyze`, `trade-quick`, `trade-technical`, `trade-fundamental`, `trade-sentiment`, `trade-earnings`, `trade-sector`, etc.)
  - Public data only; no API keys required

- **WebFetch** (Claude Code MCP tool)
  - What it's used for: Fetch full page content from financial websites, earnings transcripts, SEC filings (10-K, 10-Q), company investor relations pages
  - Invoked by: `trade-analyze`, `trade-fundamental`, `trade-earnings` skills
  - Public data only; no API keys required

**Portfolio & Cloud Services:**
- **Google Drive API** (via Claude Code MCP `mcp__claude_ai_Google_Drive__*` tools)
  - What it's used for: Read portfolio holdings from InvestmentSummary folder, upload analysis reports for archival
  - SDK/Client: Claude Code MCP (no direct SDK in this repo)
  - Auth: User's existing Anthropic API key / Claude Code session auth
  - Default folder: `InvestmentSummary` (id `1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm`)
  - Operations: `search_files`, `read_file_content`, `create_file`

- **Slack API** (via Claude Code MCP `mcp__claude_ai_Slack__slack_send_message`)
  - What it's used for: Post daily portfolio routine digests to `#portfolio-updates` channel
  - SDK/Client: Claude Code MCP (no direct SDK in this repo)
  - Auth: User's existing Anthropic API key / Claude Code session auth
  - Default channel: `#portfolio-updates` (id `C0B712ARA7M`)
  - Overridable via `/trade routine --slack-channel <id>`

## Data Storage

**Databases:**
- **Pinecone** (vector database)
  - Provider: Pinecone (serverless, cloud-managed)
  - What it stores: Chunked analysis records from `TRADE-*.md` reports (semantic vectors + metadata)
  - Connection: `PINECONE_API_KEY` environment variable (local SDK) OR `PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN` (cloud proxy)
  - Client: Pinecone Python SDK 7.3-7.x (prod); >=5 (local); installed via `pip install pinecone`
  - Default index: `trade-reports` (integrated-inference, uses `llama-text-embed-v2` embeddings)
  - Schema: Enforced via Pydantic (`scripts/trade_schemas.py` / `proxy/_lib/trade_schemas.py`)
  - Operations:
    - **Write:** `ingest` subcommand parses `TRADE-*.md`, chunks by section, generates metadata (ticker, report_type, score, grade, signal, composite_score, etc.), upserts to Pinecone
    - **Read:** `query` (semantic search), `latest` (newest record metadata), `list` (manifest), `timeline` (all tickers), `fetch` (specific record by ID)
  - Cloud transport: When `PINECONE_PROXY_URL` is set, `trade_memory.py` routes via Vercel proxy instead of direct SDK

**File Storage:**
- **Local filesystem** (user's CWD)
  - Outputs: `TRADE-ANALYSIS-<TICKER>.md`, `TRADE-QUICK-<TICKER>.md`, `TRADE-ROUTINE-<ts>.md`, `TRADE-REPORT.pdf`, etc.
  - Cache: `~/.claude/trade/TRADE-HOLDINGS.md` (fallback ticker list when Drive unavailable)
  
- **Google Drive** (InvestmentSummary folder)
  - Archive destination for: per-ticker analyses (uploaded by `/trade holdings` on first run, then by routine with `ingest --archive`)
  - Also stores: portfolio master file (`.xlsm` Excel, `.docx` docx, or broker statements in PDF)

**Caching:**
- **In-memory:** Pinecone index caches at proxy layer (`_lib/pinecone_client.py` singleton with per-index `_INDEX_CACHE`)
- **File-based:** `~/.claude/trade/TRADE-HOLDINGS.md` (ticker + position list cache for offline fallback)

## Authentication & Identity

**Auth Provider:**
- **Custom multi-layer** (producer-grade, not production-grade; intended for research tools + individual users)
  - **Local SDK mode:** Direct `PINECONE_API_KEY` in environment
  - **Cloud proxy mode:** Bearer token (`PROXY_AUTH_TOKEN`) in Vercel env, presented as `Authorization: Bearer <token>` header
  - **5-layer auth stack:**
    1. High-entropy URL (implicit in proxy endpoint)
    2. Bearer token validation (constant-time comparison in `_lib/auth.py`)
    3. Payload schema validation (Pydantic in `_lib/validate.py`)
    4. Rate limiting by client IP (in-memory sliding window in `_lib/ratelimit.py`)
    5. Monthly token rotation (manual procedure; documented in `proxy/README.md`)
  - **Deployment Protection:** Optional Vercel bypass token via `VERCEL_PROTECTION_BYPASS` env var

**MCP Tools (Claude Code):**
- **WebSearch, WebFetch, Google Drive, Slack** - all authenticated via user's existing Claude Code session
- No separate API keys needed for these; they're built into the Claude Code environment

## Monitoring & Observability

**Error Tracking:**
- Not detected (no Sentry, LogRocket, etc.)
- Errors logged to stderr with structured prefixes: `[auth]`, `[ratelimit]`, `[validate]`

**Logs:**
- **Proxy (`app.py`):** Logs auth/ratelimit/validation failures to stderr
- **Memory engine (`trade_memory.py`):** Logs progress and errors to stderr; `doctor` subcommand for health check (exits 0 healthy / 1 degraded / 2 unavailable)
- **Skills:** No explicit logging; rely on Claude Code execution context for visibility

**Health Checks:**
- `python3 scripts/trade_memory.py doctor` - Verifies SDK version, key/proxy presence, index existence, vector count, embedding-model match

## CI/CD & Deployment

**Hosting:**
- **Proxy:** Vercel (serverless Python runtime)
  - Entrypoint: `proxy/app.py` (WSGI callable)
  - Triggered by: git push to main branch
  - Vercel auto-detects Python and deploys `proxy/` as the root project

**CI Pipeline:**
- Not detected (no GitHub Actions, CircleCI, etc.)
- Manual deployment: push to main → Vercel auto-deploys proxy

**Installation:**
- **Skills/agents:** `./install.sh` copies `trade/SKILL.md`, `skills/*/SKILL.md`, `agents/*.md`, scripts into `~/.claude/`
- **Uninstall:** `./uninstall.sh` removes them (does NOT remove holdings cache `~/.claude/trade/`)

## Environment Configuration

**Required env vars:**
- **`PINECONE_API_KEY`** - API key from Pinecone (for memory features; optional if memory disabled)

**Optional env vars (defaults shown):**
- `PINECONE_INDEX` (default: `trade-reports`)
- `PINECONE_EMBED_MODEL` (default: `llama-text-embed-v2`)
- `PINECONE_CLOUD` (default: `aws`)
- `PINECONE_REGION` (default: `us-east-1`)
- `PINECONE_NAMESPACE` (default: `trade`)
- `TRADE_DRIVE_ARCHIVE_FOLDER_ID` (for Drive upload; defaults to InvestmentSummary ID if unset)
- `PINECONE_PROXY_URL` (cloud-routine only; if set, routes via proxy instead of direct SDK)
- `PINECONE_PROXY_TOKEN` (cloud-routine only; bearer token for proxy)
- `VERCEL_PROTECTION_BYPASS` (optional; for Vercel Deployment Protection bypass)
- `TRADE_SCHEMAS_PATH` (internal; path to `trade_schemas.py` for proxy validation)

**Secrets location:**
- `.env` file (gitignored, user creates from `.env.example`)
- Vercel project settings (for `PINECONE_API_KEY`, `PROXY_AUTH_TOKEN`, `VERCEL_PROTECTION_BYPASS`)

**Hardcoded destinations** (can only change via skill edits):
- Drive folder: `InvestmentSummary` (id `1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm`) in `skills/trade-holdings/SKILL.md` and `skills/trade-routine/SKILL.md`
- Slack channel: `#portfolio-updates` (id `C0B712ARA7M`) in `skills/trade-routine/SKILL.md` (overridable via CLI flag `--slack-channel`)

## Webhooks & Callbacks

**Incoming:**
- Not detected (no webhook receivers)

**Outgoing:**
- **Slack message dispatch:** `/trade routine --cloud` triggers `mcp__claude_ai_Slack__slack_send_message` to post digest to `#portfolio-updates`
- **Google Drive file creation:** `/trade routine --cloud` and `ingest --archive` trigger `mcp__claude_ai_Google_Drive__create_file` to upload reports to InvestmentSummary
- **Pinecone proxy:** When `PINECONE_PROXY_URL` is set, `trade_memory.py` makes HTTP POST requests to proxy endpoints (`/upsert`, `/query`, `/list`, `/fetch`, `/delete`) with bearer token in `Authorization` header

## Record Schema & Public Contracts

**Pinecone record format** (single source of truth: `scripts/trade_schemas.py`):
- **RecordMetadata model** with fields:
  - Identification: `id`, `namespace`, `ticker`, `company`, `report_type`, `grade`, `composite_score`, `signal`
  - Scores (0–100, except risk which is inverted): `technical_score`, `fundamental_score`, `sentiment_score`, `risk_score`, `thesis_score`
  - Metadata: `run_id`, `source_path`, `created_at`, `schema_version`
  - Options-specific (if report_type=OPTIONS): `iv_rank`, `strategy_outlook`, `position_bias`, `recommended_strategy`
  
- **Enums:**
  - `Signal`: STRONG_BUY, BUY, HOLD, NEUTRAL, CAUTION, AVOID
  - `Grade`: A+, A, B, C, D, F
  - `ReportType`: ANALYSIS, THESIS, TECHNICAL, FUNDAMENTAL, SENTIMENT, RISK, EARNINGS, QUICK, OPTIONS
  - `StrategyOutlook`: BULLISH, BEARISH, NEUTRAL, INCOME, HEDGE
  - `PositionBias`: LONG, FLAT

- **Schema versioning:** SCHEMA_VERSION = 1
  - Bumped on breaking changes only (field rename, type change, enum-value removal)
  - Additive changes (new optional fields, new enum values) do NOT bump it
  - Synced from canonical `scripts/trade_schemas.py` to proxy via `scripts/sync_proxy_schemas.sh` before each deploy
  - Proxy validates with `extra="forbid"` to prevent silent schema drift

---

*Integration audit: 2026-06-08*
