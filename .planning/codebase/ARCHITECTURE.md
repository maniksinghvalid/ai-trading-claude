# Architecture

**Analysis Date:** 2026-06-08

## System Overview

This codebase is the **source** for a Claude Code trading-research plugin system. It implements a prompt-orchestration architecture where CLI commands are routed through a hierarchical system: command router → skills → optional subagents. The system analyzes stocks and portfolios, produces markdown reports with YAML frontmatter, and optionally ingests them into a Pinecone-backed memory layer for semantic recall. **Installation is required**: `./install.sh` copies sources into `~/.claude/` where Claude Code discovers and invokes them.

```text
┌─────────────────────────────────────────────────────────────────────┐
│                  User CLI Command: /trade <command>                  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                ┌────────────▼────────────┐
                │  Orchestrator Router    │
                │  `trade/SKILL.md`       │
                │  Maps command → skill   │
                └────────────┬────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
    ┌───▼────────┐      ┌────▼─────┐        ┌────▼──────────┐
    │   Skill    │      │   Skill  │        │ Fan-Out Skill │
    │  (Simple)  │      │ (Analyze)│        │  (invokes 5   │
    │            │      │          │        │   subagents)  │
    └───┬────────┘      └────┬─────┘        └───┬────────────┘
        │                    │                   │
        │            ┌───────▼────────┐         │
        │            │ PHASE 1:       │         │
        │            │ Discovery      │         │
        │            │ (gather data)  │         │
        │            └────────┬───────┘         │
        │                     │                 │
        │            ┌────────▼────────┐       │
        │            │ PHASE 2:        │       │
        │            │ Parallel Agents │◄──────┘
        │            │ (5 concurrent)  │
        │            └────────┬────────┘
        │                     │
        │            ┌────────▼────────┐
        │            │ PHASE 3:        │
        │            │ Synthesis       │
        │            │ (combine scores)│
        │            └────────┬────────┘
        │                     │
        └─────────────────────┼─────────────────┐
                              │                 │
                        ┌─────▼──────┐    ┌────▼──────────┐
                        │   Report   │    │ Optional:     │
                        │   (CWD)    │    │ Ingest Memory │
                        └────────────┘    └────┬──────────┘
                                               │
                                    ┌──────────▼──────────┐
                                    │  trade_memory.py   │
                                    │  (producer side)   │
                                    └──────────┬─────────┘
                                               │
                        ┌──────────────────────┼──────────────────────┐
                        │                      │                      │
                  ┌─────▼──────┐        ┌─────▼──────┐      ┌────────▼───┐
                  │   Proxy    │        │  Pinecone  │      │  Recall    │
                  │ (Vercel)   │────────│  Index     │      │  Consumer  │
                  └────────────┘        └────────────┘      └────────────┘
                  Holds API key        Vector DB,          trade-recall
                                       semantic search      skill
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Orchestrator | Routes `/trade <command>` to appropriate skill; documents all 19 commands | `trade/SKILL.md` |
| Analyze Skill | Implements 3-phase flow (Discovery → Parallel agents → Synthesis) | `skills/trade-analyze/SKILL.md` |
| Technical Agent | Analyzes price action, indicators, patterns; returns technical score | `agents/trade-technical.md` |
| Fundamental Agent | Analyzes valuation, growth, profitability, moat; returns fundamental score | `agents/trade-fundamental.md` |
| Sentiment Agent | Analyzes news, social, analyst ratings, insider activity; returns sentiment score | `agents/trade-sentiment.md` |
| Risk Agent | Analyzes volatility, downside, macro sensitivity, liquidity; returns risk score (inverted) | `agents/trade-risk.md` |
| Thesis Agent | Synthesizes bull/bear cases, catalysts, entry/exit; returns thesis score | `agents/trade-thesis.md` |
| Quick Skill | Fast 60-second assessment without agents; terminal output | `skills/trade-quick/SKILL.md` |
| Other Skills | 18 specialized commands (technical, fundamental, sentiment, sector, compare, thesis, options, portfolio, holdings, routine, recall, risk, screen, earnings, watchlist, report-pdf, 2 more) | `skills/trade-*/SKILL.md` |
| Routine Skill | Tiered daily sweep of portfolio; dispatches analyze/quick per ticker; options overlay | `skills/trade-routine/SKILL.md` |
| Recall Skill | Semantic search over Pinecone-indexed reports; returns cited findings with attribution | `skills/trade-recall/SKILL.md` |
| Memory Producer | Ingests reports into Pinecone; validates schema; writes archival metadata | `scripts/trade_memory.py` |
| Memory Proxy | Vercel serverless function; holds Pinecone API key; exposes REST endpoints to cloud routines | `proxy/app.py` + `proxy/api/` |
| PDF Generator | Renders TRADE-ANALYSIS reports to professional PDF | `scripts/generate_trade_pdf.py` |
| Scoring Utilities | Scoring weights, grade/signal lookup, shared formulas | `scripts/trade_scoring.py` |
| Schema Registry | Pinecone record format; shared by producer and proxy | `scripts/trade_schemas.py` |

## Pattern Overview

**Overall:** Hierarchical prompt orchestration with agent fan-out and memory integration.

**Key Characteristics:**
- **Prompt-based, not code-based**: Skills and agents are Markdown prompts with YAML frontmatter (`name:`, `description:`), not Python/TypeScript functions
- **Single responsibility per skill**: Each `/trade` command has one skill; each skill does one thing well
- **Parallel multi-agent analysis**: The `/trade analyze` command launches 5 agents **simultaneously** to analyze different dimensions, then synthesizes their scores
- **Report-centric output**: All skills write Markdown reports to `cwd` with YAML frontmatter; frontmatter enables automated schema validation and Pinecone ingestion
- **Optional memory layer**: Reports can be indexed into Pinecone; users query them via `/trade recall`; memory is optional (graceful degradation if Pinecone unavailable)
- **Schema-driven validation**: Reports validate against `scripts/trade_schemas.py`; the proxy re-validates before Pinecone write
- **Separation of local and cloud**: `trade_memory.py` (local, runs in routine's sandbox) writes to proxy; proxy holds API key and forwards to Pinecone

## Layers

**Orchestrator Layer:**
- Purpose: Route `/trade <command>` to the correct skill; document all 19 commands and their outputs
- Location: `trade/SKILL.md`
- Contains: Command routing table, scoring methodology, output standards, disclaimer
- Depends on: Nothing (entry point)
- Used by: Claude Code runtime (when user invokes `/trade`)

**Skills Layer:**
- Purpose: Implement specific trading research commands (analyze, quick, technical, fundamental, sentiment, sector, compare, thesis, options, portfolio, holdings, routine, recall, risk, screen, earnings, watchlist, report-pdf)
- Location: `skills/trade-*/SKILL.md` (18 directories, each with a single SKILL.md file)
- Contains: Execution logic, search patterns, output formats, terminal rendering
- Depends on: WebSearch, WebFetch, Bash, optional Agent tool (analyze only)
- Used by: Orchestrator, users (indirectly via routing)

**Agent Subagent Layer:**
- Purpose: Perform parallel specialized analysis on a single dimension (technical, fundamental, sentiment, risk, thesis); return structured scores and findings
- Location: `agents/trade-{technical,fundamental,sentiment,risk,thesis}.md` (5 files)
- Contains: Specialized prompts for one dimension; 5-20 subscore breakdown; analysis sections; citation requirements
- Depends on: WebSearch, WebFetch, discovery data from Phase 1 (passed as context)
- Used by: `/trade analyze` skill (Phase 2, launched in parallel)

**Report Output Layer:**
- Purpose: Markdown files with YAML frontmatter, written to `cwd`; semantic indexing into Pinecone
- Location: `cwd` (wherever user runs `/trade` command) + `~/.claude/trade/` (cache directory for holdings)
- Contains: Report filename pattern `TRADE-<REPORT_TYPE>-<TICKER>[-<ts>].md`; YAML frontmatter with `trade_report: true`, schema_version, ticker, report_type, generated_at, scores, signal, grade, and dimension-specific fields
- Depends on: Skills (write to CWD); memory producer (optional ingest)
- Used by: Recall skill, users (read CWD), optional Pinecone indexing

**Memory Layer:**
- Purpose: Ingest reports into Pinecone; query via semantic search; persist portfolio context
- Location: Producer script (`scripts/trade_memory.py`), Pinecone backend (external), Vercel proxy (`proxy/`)
- Contains: Ingest, query, list, fetch, delete operations; schema validation; support for multiple namespaces (per portfolio/context)
- Depends on: Pinecone SDK, HTTP client, `scripts/trade_schemas.py` (schema validation)
- Used by: `/trade routine` (ingest phase), `/trade recall` (query phase)

**Proxy Layer (Cloud Integration):**
- Purpose: Hold Pinecone API key in Vercel env; validate payloads; forward to Pinecone; isolate local code from secrets
- Location: `proxy/` (separate Vercel project directory)
- Contains: Flask-like app with 5 endpoints (`/upsert`, `/query`, `/list`, `/fetch`, `/delete`); Bearer auth; schema re-validation
- Depends on: Pinecone SDK, Bearer token (from Vercel env vars), schema validation
- Used by: `trade_memory.py` (when run in cloud routine), `/trade recall` (if cloud-mode)

**Utilities Layer:**
- Purpose: Shared logic for scoring, PDF generation, schema management, installation
- Location: `scripts/` (trade_memory.py, generate_trade_pdf.py, trade_scoring.py, trade_schemas.py, shell sync scripts) + `install.sh`, `uninstall.sh`
- Contains: Scoring weights and grade/signal lookup (shared by all skills), Pinecone schema definition, PDF rendering logic, installation/uninstallation logic
- Depends on: Python stdlib, reportlab (for PDF), pinecone SDK (optional)
- Used by: Skills (scoring), memory producer (schema), PDF skill, orchestrator (installation reference)

## Data Flow

### Primary Request Path: `/trade analyze <TICKER>`

1. **Entry** (`trade/SKILL.md:35-47`) — Orchestrator receives `/trade analyze AAPL` and routes to `skills/trade-analyze/SKILL.md`

2. **Phase 1: Discovery** (`skills/trade-analyze/SKILL.md:18-74`) — Analyze skill performs direct research (no agents yet):
   - WebSearch for current price, market cap, 52-week range, sector, index context
   - WebSearch for company description, products, leadership, employee count
   - WebSearch for recent news, catalysts, earnings dates, major announcements, macro headwinds
   - WebSearch for key financials: P/E, revenue, EPS, margins, debt, FCF, dividend, short interest
   - Compile all findings into `DISCOVERY_BRIEF` (structured text block)

3. **Phase 2: Parallel Agent Deployment** (`skills/trade-analyze/SKILL.md:76-394`) — Analyze skill launches 5 agents **in a single message** (all parallel):
   - Each agent receives: full `DISCOVERY_BRIEF` + specialized mandate + instruction to return structured score
   - **Agent 1 (Technical)** → analyzes trend, support/resistance, momentum, volume, patterns → returns Technical Score 0-100
   - **Agent 2 (Fundamental)** → analyzes valuation, growth, profitability, financial health, moat → returns Fundamental Score 0-100
   - **Agent 3 (Sentiment)** → analyzes news, social, analysts, institutional, insider, short interest → returns Sentiment Score 0-100
   - **Agent 4 (Risk)** → analyzes volatility, downside, macro, liquidity, position sizing → returns Risk Score 0-100 (inverted: higher = lower risk)
   - **Agent 5 (Thesis)** → synthesizes bull/bear cases, catalysts, entry/exit, conviction → returns Thesis Score 0-100
   - All 5 return structured findings formatted with `## <Name> Analysis: <TICKER>`, score breakdown, signal, and detailed sections

4. **Phase 3: Synthesis** (`skills/trade-analyze/SKILL.md:396-`) — Analyze skill combines 5 scores into composite:
   - Composite Trade Score = (Tech × 0.25) + (Fundamental × 0.25) + (Sentiment × 0.20) + (Risk × 0.15) + (Thesis × 0.15)
   - Determine grade and signal from score range (85+/A+/Strong Buy, 70-84/A/Buy, 55-69/B/Hold, 40-54/C/Neutral, 25-39/D/Caution, 0-24/F/Avoid)
   - Write `TRADE-ANALYSIS-<TICKER>.md` to CWD with YAML frontmatter including all 5 dimension scores, composite score, signal, grade
   - Frontmatter enables `trade_memory.py ingest` to parse and validate; Pinecone index stores all fields for recall

### Secondary Flow: `/trade routine` (Portfolio Sweep)

1. **Pre-flight** (`skills/trade-routine/SKILL.md:47-146`) — Routine skill:
   - Parse flags (`--max-escalations N`, `--cloud`, `--slack-channel`, `--no-options`)
   - Generate `run_id` = `routine-<YYYYMMDD-HHMM>-<6hex>`
   - Load holdings via `/trade holdings` skill or fall back to cache
   - Initialize counters for escalation budgeting

2. **Per-ticker loop** (`skills/trade-routine/SKILL.md:113-`) — For each ticker in holdings:
   - Step 1: Call `trade_memory.py recommend-tier <TICKER>` → returns `analyze` or `quick` (based on staleness + signal history)
   - Step 2: Fetch prior record via `trade_memory.py latest <TICKER>` (for delta reporting)
   - Step 3a: If tier=analyze AND escalations_used < max_escalations: dispatch `/trade analyze <TICKER>`, increment counter, ingest result
   - Step 3b: If tier=quick OR escalation capped: dispatch `/trade quick <TICKER>`, skip ingest (or do quick ingest)
   - Step 3c (optional): If ticker received an analyze AND no-options flag not set: dispatch `/trade options <TICKER>` for position-aware overlay; ingest `OPTIONS` record
   - Step 4: Aggregate ticker result (prior vs current signal, score delta, tier used) into digest row

3. **Post-sweep** (`skills/trade-routine/SKILL.md:-`) — Routine skill:
   - Write `TRADE-ROUTINE-<ts>.md` to CWD with summary table (all tickers, prior/current signal, delta, errors)
   - If `--cloud` flag set: post digest to Slack `#portfolio-updates`, upload full report to Drive `InvestmentSummary` folder
   - Non-fatal failures in cloud delivery leave local outputs intact

### Tertiary Flow: `/trade recall "<query>"` (Memory Recall)

1. **Pre-flight** (`skills/trade-recall/SKILL.md:41-58`) — Recall skill:
   - Run `trade_memory.py doctor` to health-check Pinecone connection
   - If unreachable: offer degraded fallback (list local TRADE-*.md files in CWD)

2. **Query** (`skills/trade-recall/SKILL.md:59-71`) — If memory available:
   - Call `trade_memory.py query "<query>" [--ticker <T>] [--type <TYPE>] -n <N>` 
   - Pinecone performs semantic search on indexed report text chunks; returns top-N hits with metadata

3. **Render** (`skills/trade-recall/SKILL.md:72-97`) — For each hit, emit citation:
   ```
   From TRADE-<REPORT_TYPE>-<TICKER> (<YYYY-MM-DD>):
   > "<verbatim quote from chunk>"
   > — section: <section-slug>, score: <hit_score>
   ```
   - Every quote includes report type, ticker, date, section, and similarity score
   - No paraphrasing; verbatim text preservation ensures accuracy

**State Management:**
- **Local state**: CWD (report files written during command execution); `~/.claude/trade/TRADE-HOLDINGS.md` (portfolio cache)
- **Cloud state**: Pinecone index (one or more namespaces); Drive `InvestmentSummary` folder (report archive); Slack `#portfolio-updates` (digest feed)
- **Transient state**: `DISCOVERY_BRIEF` in analyze Phase 1 (scoped to single message, passed to Phase 2 agents)

## Key Abstractions

**DISCOVERY_BRIEF:**
- Purpose: Structured context block compiled in `/trade analyze` Phase 1; passed to all 5 Phase 2 agents to prevent redundant searches
- Examples: Current price, market cap, P/E, revenue, latest news, earnings date, macro context
- Pattern: Plain text block organized into sections (Price Context, Company Overview, Recent News, Key Metrics); agents parse and extract as needed

**TRADE SCORE:**
- Purpose: Normalized 0-100 rating of a stock's attractiveness; synthesized from multiple dimensions
- Examples: Composite score (weighted average of 5 dimensions), dimension-specific scores (technical, fundamental, etc.), quick-snapshot signal (Buy/Hold/Sell/Avoid)
- Pattern: Every report includes a score; `/trade analyze` combines 5 dimension scores; `/trade quick` emits a signal (not a numeric score, but ordered: Buy > Hold > Sell > Avoid)

**PINECONE NAMESPACE:**
- Purpose: Logical partition of the Pinecone index; typically one per portfolio or context
- Examples: `trade` (default), `test`, `portfolio-user1`, etc.
- Pattern: `/trade routine` ingests under `run_id` namespace by default (or can override); `/trade recall` can query specific namespace

**REPORT FRONTMATTER:**
- Purpose: YAML metadata block at top of every report; enables schema validation and Pinecone ingestion
- Examples: `trade_report: true`, `schema_version: 1`, `ticker: AAPL`, `report_type: ANALYSIS`, `composite_score: 82`, `signal: BUY`, `grade: A`, plus dimension-specific fields
- Pattern: All skills that write reports include frontmatter; `trade_memory.py ingest` parses and validates; proxy re-validates on cloud path

## Entry Points

**CLI Entry: `/trade <command> [args]`** (`trade/SKILL.md`)
- Triggers: User invocation in Claude Code terminal
- Responsibilities: Route to appropriate skill; document all 19 commands
- Output: Dispatches to skill (which may write file, invoke agents, return terminal output)

**Skill Entry: `/trade analyze <ticker>`** (`skills/trade-analyze/SKILL.md`)
- Triggers: Orchestrator routing OR direct user invocation (e.g., `claude code` with multi-step planning)
- Responsibilities: 3-phase flow (Discovery → Parallel agents → Synthesis); composite scoring; report generation
- Output: `TRADE-ANALYSIS-<TICKER>.md` with 5 dimension scores, composite score, signal, grade

**Skill Entry: `/trade quick <ticker>`** (`skills/trade-quick/SKILL.md`)
- Triggers: User (fast snapshot) OR routine (when tier=quick)
- Responsibilities: Fast 60-second assessment without agents
- Output: Terminal output (no file written); used by routine for signal delta detection

**Skill Entry: `/trade routine [flags]`** (`skills/trade-routine/SKILL.md`)
- Triggers: User (`/trade routine`), with optional flags (`--max-escalations`, `--cloud`, `--no-options`)
- Responsibilities: Tiered portfolio sweep; escalation budgeting; options overlay; cloud delivery
- Output: `TRADE-ROUTINE-<ts>.md`, per-ticker analyze/quick/options reports, optional Slack/Drive upload

**Skill Entry: `/trade recall "<query>" [args]`** (`skills/trade-recall/SKILL.md`)
- Triggers: User (semantic search over past analyses)
- Responsibilities: Health-check memory layer; query Pinecone; render cited findings
- Output: Terminal output (cited findings block)

**Memory Producer Entry: `python3 trade_memory.py ingest <report>`** (`scripts/trade_memory.py`)
- Triggers: Skills/routine after report generation
- Responsibilities: Parse report frontmatter; validate schema; upsert to Pinecone (or proxy); archive metadata
- Output: Ingestion confirmation + error handling

**Memory Query Entry: `python3 trade_memory.py query "<q>" [args]`** (`scripts/trade_memory.py`)
- Triggers: `/trade recall` skill
- Responsibilities: Semantic search on indexed chunks
- Output: Hit list with metadata and text snippets

## Architectural Constraints

- **Threading:** Single-threaded event loop (Claude Code/Agent tool is inherently sequential per response). Parallel agents in Phase 2 achieve concurrency via single Agent tool message containing all 5 agent definitions — Claude's runtime processes them in parallel.
- **Global state:** No persistent global state in code. All state is file-based (CWD reports, `~/.claude/trade/` cache) or external (Pinecone index, Drive folder, Slack channel). This enables loose coupling and fault isolation.
- **Circular imports:** No imports in Markdown prompts. Skills/agents are isolated prompts, not Python modules.
- **Secrets:** Pinecone API key is **never** embedded in prompt or local script. Instead, it lives in Vercel env vars (`proxy/`), and local code (`trade_memory.py`) authenticates to proxy via Bearer token (`PINECONE_PROXY_TOKEN`), which is acceptable in local-only context (Vercel routing prevents key leakage).
- **Escalation budgeting:** `/trade routine` caps the number of full `/trade analyze` dispatches per sweep via `--max-escalations` flag (default 10). Tickers exceeding the cap receive `/trade quick` instead, maintaining sweep performance for large portfolios.
- **Schema versioning:** Pinecone record schema is versioned via `schema_version` field in frontmatter. Additive changes (new fields) don't require bumping; field renames or type changes do. The schema is single-sourced in `scripts/trade_schemas.py` and re-validated by proxy.
- **Graceful degradation:** All memory access (ingest, query) is optional. If Pinecone unavailable, local skills complete normally (reports still written to CWD); recall skill offers file-based fallback; routine continues without ingestion.
- **Installation coupling:** Skills and agents don't auto-discover. `install.sh` hardcodes the list of skills/agents to install into `~/.claude/`. Adding a skill requires editing both `install.sh` and `uninstall.sh` (arrays `SKILLS` and `AGENTS`), plus updating command reference.

## Anti-Patterns

### Over-Parallelizing Non-Analysis Commands

**What happens:** A developer sees the 5-agent pattern in `/trade analyze` and tries to parallelize other commands (e.g., `/trade quick`, `/trade technical`). Quick snapshots launch independent WebSearch queries in parallel, but the skill doesn't await them properly.

**Why it's wrong:** Claude Code's Agent tool is already concurrent (all agents in one message run in parallel). Launching WebSearch in quick creates false parallelism — WebSearch itself is a single request that cannot be sub-parallelized. This adds latency without benefit.

**Do this instead:** Launch all WebSearch queries in a **single message** (not via Agent tool, just inline `WebSearch` tool calls). Then process results sequentially. See `skills/trade-quick/SKILL.md:20-48` for the correct pattern.

### Storing Pinecone Key Locally

**What happens:** A developer embeds `PINECONE_API_KEY` in a local prompt or script for convenience.

**Why it's wrong:** The key is a production secret; embedding it in code (even private repos) is a security anti-pattern. Local code that doesn't need the key (only proxy does) should never hold it.

**Do this instead:** Store the key in Vercel env vars (`proxy/`); local code (`trade_memory.py`, skills) authenticate to proxy via `PINECONE_PROXY_TOKEN` (an auth token, not the master key). This way, a compromised local machine doesn't expose the Pinecone account.

### Hardcoding Namespace in Prompts

**What happens:** A skill hardcodes `namespace: "trade"` when calling Pinecone, instead of respecting the routine's `run_id` or allowing customization.

**Why it's wrong:** Multiple portfolios or contexts need separate namespaces. Hardcoding prevents multitenant use. The namespace should be parameterized.

**Do this instead:** Accept namespace as a flag or env var; default to `run_id` in routine context. See `skills/trade-routine/SKILL.md:66` (`RUN_ID` generation) and `scripts/trade_memory.py ingest --namespace` pattern.

### Duplicating Scoring Weights Across Files

**What happens:** Scoring weights (Technical 25%, Fundamental 25%, Sentiment 20%, Risk 15%, Thesis 15%) are hardcoded in multiple files (README, orchestrator, analyze skill, agents).

**Why it's wrong:** Weight changes require edits in 4+ places. Missing one causes inconsistency; composite score formula no longer matches documented weights.

**Do this instead:** Single source of truth in `scripts/trade_scoring.py`. All skills import from there (though they can't Python-import in prompts, so they reference the file in prose). Grade/signal lookup is also centralized there. See `scripts/trade_scoring.py` and the cross-file contract in `CLAUDE.md`.

### Merging Skill and Agent Prompts

**What happens:** A developer combines `/trade technical <ticker>` (a standalone skill) with the **technical agent** (a subagent invoked by analyze) into a single prompt.

**Why it's wrong:** The standalone skill and the agent have different contexts. The agent receives `DISCOVERY_BRIEF` (shared context from Phase 1) and returns a structured score. The skill does its own discovery and may write a different format. Merging breaks the Phase 2 fan-out model.

**Do this instead:** Keep them separate and synchronized. Methodology should be consistent, but prompts are distinct. If you update one, update the other. See `agents/trade-technical.md` vs `skills/trade-technical/SKILL.md`.

---

*Architecture analysis: 2026-06-08*
