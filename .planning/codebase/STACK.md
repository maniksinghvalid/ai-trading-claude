# Technology Stack

**Analysis Date:** 2026-06-08

## Languages

**Primary:**
- **Python** 3.8+ - Executable backend scripts (`scripts/`, `proxy/`): PDF generation, memory engine, schema validation, scoring, Vercel serverless functions
- **Markdown** - Prompt-suite definition language: 19 skills (`skills/*/SKILL.md`), 5 agents (`agents/*.md`), 1 orchestrator (`trade/SKILL.md`). First-class part of the codebase; not documentation.

**Secondary:**
- **Shell (bash/zsh)** - Installation scripts (`install.sh`, `uninstall.sh`), helper utilities
- **JSON** - Configuration, API payloads, schema definitions

## Runtime

**Environment:**
- **Local execution:** Python 3.8+ interpreter (user's system)
- **Cloud execution:** Vercel Python runtime (serverless functions, WSGI)

**Package Manager:**
- **pip** (Python package manager)
- **Lockfile:** `requirements.txt` (root) and `proxy/requirements.txt` (proxy-specific)
- **Version pinning strategy:** MAJOR version pins in proxy (`pinecone>=7.3,<8`) to avoid runtime contract breakage; loose pins in root (`reportlab>=4.0`, `pinecone>=5`, `pydantic>=2`) for local use

## Frameworks

**Core:**
- **WSGI** (Python Web Server Gateway Interface) - HTTP framework for Vercel proxy; bare WSGI (`app.py` callable) rather than Django/Flask; handles 5 endpoints (`/upsert`, `/query`, `/list`, `/fetch`, `/delete`)
- **Pydantic** 2.x - Schema validation and serialization; enforces record contract at proxy boundary (`validate.py` re-validates with `extra="forbid"`)

**Data & Storage:**
- **Pinecone SDK** 7.3-7.x (prod) / >=5 (local) - Serverless vector database client for semantic search over historical analyses
  - Uses integrated-inference for embeddings (`llama-text-embed-v2` model)
  - Dual transport: direct SDK (`PINECONE_API_KEY`) or proxy (`PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN`)

**PDF Generation:**
- **reportlab** 4.0+ - Professional PDF rendering; used by `scripts/generate_trade_pdf.py` to produce 6-page investment reports with charts, gauges, tables

**Code Execution & Utilities:**
- **importlib.util** (stdlib) - Module dynamic loading for sibling imports (`generate_trade_pdf.py`, `trade_memory.py` load `trade_scoring.py` and `trade_schemas.py` by absolute path; works from any CWD or install location)
- **argparse** (stdlib) - CLI argument parsing in `trade_memory.py`
- **json, re, pathlib, datetime, os** (stdlib) - Utility modules throughout

## Key Dependencies

**Critical:**
- **pinecone** 7.3-7.x - Vector database client; invoked by `/trade routine` (daily portfolio sweep), `/trade recall` (semantic search over past analyses), and routine's options-overlay Step 3d. Slice 3a + 7.5 features degrade gracefully if unavailable; core `/trade analyze`, `/trade quick` work without it.
- **pydantic** 2.x - Validates every Pinecone record before upsert (local path via `scripts/trade_schemas.py`) and at proxy boundary (vendored copy via `proxy/_lib/trade_schemas.py`). Single source of truth: `scripts/trade_schemas.py` → synced to proxy via `scripts/sync_proxy_schemas.sh` before each deploy.
- **reportlab** 4.0+ - `/trade report-pdf` skill depends on this; core analysis skills work without it (PDF is optional output).

**Infrastructure:**
- **Vercel platform** - Serverless execution for proxy (not a pip dependency; deployment platform)
- **Google Drive API** (via Claude Code MCP `mcp__claude_ai_Google_Drive__*` tools) - `/trade holdings` reads portfolio from Drive folder `InvestmentSummary` (id `1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm`)
- **Slack API** (via Claude Code MCP `mcp__claude_ai_Slack__slack_send_message`) - `/trade routine --cloud` posts digest to `#portfolio-updates`
- **WebSearch** (Claude Code MCP) - All analysis skills use WebSearch to gather public market data (no market-data API keys required)
- **WebFetch** (Claude Code MCP) - Fetches earnings transcripts, SEC filings, company websites

## Configuration

**Environment:**
- **`.env` file** (gitignored, `.env.example` template provided)
  - **Required:** `PINECONE_API_KEY` (for memory/routine features)
  - **Optional:** `PINECONE_INDEX`, `PINECONE_EMBED_MODEL`, `PINECONE_CLOUD`, `PINECONE_REGION`, `PINECONE_NAMESPACE`
  - **Cloud-routine only:** `PINECONE_PROXY_URL`, `PINECONE_PROXY_TOKEN`, `VERCEL_PROTECTION_BYPASS`

- **Hardcoded destinations** (in skill prose, no config file):
  - Drive folder: `InvestmentSummary` (id `1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm`)
  - Slack channel: `#portfolio-updates` (id `C0B712ARA7M`)
  - Both overridable at skill invoke time (`--slack-channel <id>` for routine)

**Build/Install:**
- **`install.sh`** - Copies skills, agents, scripts into `~/.claude/` (re-run to update)
- **`uninstall.sh`** - Removes installed skills/agents/scripts from `~/.claude/`
- File list hardcoded in both scripts; adding a skill requires edits to both plus README updates

**Proxy deployment:**
- **`proxy/vercel.json`** - Empty (Vercel auto-detects Python entrypoint)
- **`proxy/requirements.txt`** - Pinned to `pinecone>=7.3,<8` (major version lock to prevent SDK breakage at deploy time)
- **`proxy/.env.example`** - Documents required env vars: `PINECONE_API_KEY`, `PROXY_AUTH_TOKEN`

## Platform Requirements

**Development:**
- Python 3.8+
- Bash/zsh shell
- Git (for repo cloning)
- reportlab (`pip install reportlab` - optional, for PDF generation)
- pinecone + pydantic (`pip install 'pinecone>=7.3,<8' pydantic` - optional, for memory features)

**Production (Cloud):**
- **Hosting:** Vercel (serverless Python runtime)
- **Vector database:** Pinecone (cloud-managed)
- **Storage:** Google Drive (portfolio holdings)
- **Messaging:** Slack (digest delivery)

**Authentication:**
- **Pinecone:** Bearer token (API key) in `PROXY_AUTH_TOKEN` env var on proxy
- **Vercel:** Deployment Protection bypass token (optional, if enabled on project)
- **Google Drive:** via Claude Code MCP auth (user's existing Anthropic auth)
- **Slack:** via Claude Code MCP auth (user's existing Anthropic auth)

## Execution Model

**Prompt-suite architecture:**
- Markdown skills/agents are Markdown prompts that Claude Code routes to and executes
- `/trade <command>` maps to a skill in `skills/<command>/SKILL.md` or a direct agent dispatch
- Orchestrator (`trade/SKILL.md`) routes 15 public commands + parallel fan-out for `/trade analyze`

**Executable surfaces:**
1. **PDF generator:** `python3 scripts/generate_trade_pdf.py [data.json] [output.pdf]`
   - Demo mode (no args): generates sample PDF
   - Real data mode: reads JSON payload from arg 1, writes to arg 2
   
2. **Memory engine:** `python3 scripts/trade_memory.py <subcommand> [args]`
   - Subcommands: `init`, `ingest`, `query`, `latest`, `list`, `timeline`, `delete`, `rebuild`, `recommend-tier`, `doctor`
   - Supports local SDK or cloud proxy transport
   
3. **Proxy:** WSGI app deployed to Vercel
   - Entrypoint: `proxy/app.py` (WSGI callable)
   - Endpoints: POST `/upsert`, `/query`, `/list`, `/fetch`, `/delete`
   - Auth stack: bearer token → rate limit → JSON parse → per-endpoint validation

---

*Stack analysis: 2026-06-08*
