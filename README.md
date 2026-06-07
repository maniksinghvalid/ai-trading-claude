<p align="center">
  <img src=".github/banner.svg" alt="AI Trading Analyst for Claude Code" width="900"/>
</p>

<p align="center">
  <strong>AI Trading Analyst for Claude Code.</strong> Run full stock analyses with 5 parallel agents, build investment theses,<br/>
  assess risk, screen for opportunities, analyze options, run tiered daily portfolio routines, and recall past findings via a Pinecone vector store — 19 skills, 5 agents, one command.
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"/></a>
  <img src="https://img.shields.io/badge/Skills-19-blue" alt="19 Skills"/>
  <img src="https://img.shields.io/badge/Memory-Pinecone-purple" alt="Pinecone-backed memory"/>
  <img src="https://img.shields.io/badge/Agents-5-orange" alt="5 Agents"/>
  <img src="https://img.shields.io/badge/Options-Analysis-green" alt="Options Analysis"/>
  <img src="https://img.shields.io/badge/Python-3.8+-blue" alt="Python 3.8+"/>
  <img src="https://img.shields.io/badge/PDF-Reports-red" alt="PDF Reports"/>
</p>

---

> **WARNING: This tool is for educational and research purposes only. It is NOT financial advice. It does NOT execute trades. It does NOT manage money. Always do your own due diligence and consult a licensed financial advisor before making investment decisions.**

---

## Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/maniksinghvalid/ai-trading-claude/main/install.sh | bash
```

That's it. One command installs all 19 skills, 5 agents, the PDF generation scripts, and the Pinecone vector-memory CLI (`trade_memory.py`). Pinecone setup is optional and gated — see [Vector Memory (Pinecone)](#vector-memory-pinecone) below.

---

## What Is This?

AI Trading Analyst is a **research and analysis tool** built as Claude Code skills. It is **not** a trading bot. It does **not** connect to brokerages. It does **not** execute trades.

What it does: takes a ticker symbol and runs a comprehensive multi-dimensional analysis using 5 parallel AI agents — technical, fundamental, sentiment, risk, and thesis — then produces a composite Trade Score (0-100) with a clear signal (Strong Buy / Buy / Hold / Neutral / Caution / Avoid).

Run `/trade analyze AAPL` and 5 AI agents launch in parallel to produce a complete investment research report.

No API keys. No brokerage accounts. No financial data subscriptions. Just Claude Code.

---

## Architecture

```
                         /trade analyze <ticker>
                                 |
                   ┌─────────────┼─────────────┐
                   |             |             |
             ┌─────┴──────┐ ┌───┴─────┐ ┌─────┴──────┐
             | trade-      | | trade-  | | trade-     |
             | technical   | | funda-  | | sentiment  |
             | agent       | | mental  | | agent      |
             | (price,     | | agent   | | (news,     |
             |  patterns,  | | (value, | |  social,   |
             |  indicators)| |  growth)| |  analysts) |
             └─────────────┘ └────────┘ └────────────┘
                   |             |             |
             ┌─────┴──────┐ ┌───┴─────┐
             | trade-risk  | | trade-  |
             | agent       | | thesis  |
             | (volatility,| | agent   |
             |  sizing,    | | (bull/  |
             |  drawdown)  | |  bear,  |
             |             | |  entry) |
             └─────────────┘ └────────┘
                   |             |             |
                   └─────────────┼─────────────┘
                                 |
                   ┌─────────────┴─────────────┐
                   |   Composite Trade Score    |
                   |   (0-100) + Grade + Signal |
                   |   + PDF Investment Report  |
                   └───────────────────────────┘
```

---

## All 19 Commands

### Analysis & Research

| Command | What It Does |
|---------|-------------|
| `/trade analyze <ticker>` | **Flagship** — Full stock analysis with 5 parallel agents. Returns Trade Score (0-100), technical levels, fundamental metrics, sentiment reading, risk profile, investment thesis, and entry/exit plan. |
| `/trade quick <ticker>` | 60-second stock snapshot — price, trend, key metrics, signal. No subagents. |
| `/trade technical <ticker>` | Technical analysis — price action, chart patterns, indicators, support/resistance levels. |
| `/trade fundamental <ticker>` | Fundamental analysis — financials, valuation metrics, competitive moat, growth trajectory. |
| `/trade sentiment <ticker>` | News and social sentiment — analyst ratings, insider activity, social buzz, news tone. |
| `/trade sector <sector>` | Sector rotation and momentum — relative strength, fund flows, top/bottom performers. |

### Thesis & Strategy

| Command | What It Does |
|---------|-------------|
| `/trade thesis <ticker>` | Complete investment thesis — bull/bear cases, catalysts, entry/exit strategy with price levels. |
| `/trade compare <t1> <t2>` | Head-to-head stock comparison across all dimensions with a winner recommendation. |
| `/trade options <ticker>` | Options strategy recommendations — covered calls, spreads, protective puts based on outlook. |
| `/trade earnings <ticker>` | Pre-earnings analysis — expected move, historical reactions, positioning strategy. |

### Portfolio & Risk

| Command | What It Does |
|---------|-------------|
| `/trade portfolio` | Portfolio analysis — correlation matrix, sector exposure, rebalancing recommendations. |
| `/trade holdings` | Read your holdings from Google Drive (InvestmentSummary folder by default), normalize, dedup, cache to `~/.claude/trade/TRADE-HOLDINGS.md` for offline fallback. |
| `/trade routine` | Tiered daily sweep over your holdings — full `/trade analyze` for stale tickers, `/trade quick` for fresh ones, escalation when a quick reveals a signal change. Emits a `TRADE-ROUTINE-<ts>.md` digest. Add `--cloud` to also post the digest to Slack `#portfolio-updates` + upload to Drive InvestmentSummary. |
| `/trade risk <ticker>` | Risk assessment — position sizing, max drawdown, scenario analysis, risk/reward ratio. |
| `/trade screen <criteria>` | Stock screener — filter by strategy (momentum, value, dividend, growth, etc.). |
| `/trade watchlist` | Build and update a scored watchlist with ranked opportunities. |

### Memory & Recall

| Command | What It Does |
|---------|-------------|
| `/trade recall "<query>" [TICKER]` | Semantic search over your past `TRADE-*.md` analyses (Pinecone-backed). Returns cited findings with the source filename, date, report type, and section. Treats ingested text as **reference material to evaluate, not instructions to follow**. |

### Reporting

| Command | What It Does |
|---------|-------------|
| `/trade report-pdf` | Professional 6-page PDF investment report with score gauges, charts, and thesis. |

---

## Scoring Methodology

The **Trade Score** (0-100) is a weighted composite of 5 dimensions:

| Category | Weight | What It Measures |
|----------|--------|------------------|
| Technical Strength | 25% | Trend, momentum, volume, pattern quality, support/resistance |
| Fundamental Quality | 25% | Valuation, growth, profitability, balance sheet, moat |
| Sentiment & Momentum | 20% | News tone, social buzz, analyst consensus, insider signals |
| Risk Profile | 15% | Volatility, drawdown potential, correlation, liquidity |
| Thesis Conviction | 15% | Catalyst clarity, timeline, asymmetry, edge identification |

### Grade & Signal Interpretation

| Score | Grade | Signal | Meaning |
|-------|-------|--------|---------|
| 85-100 | A+ | Strong Buy | High conviction across all dimensions |
| 70-84 | A | Buy | Favorable setup with manageable risks |
| 55-69 | B | Hold | Mixed signals, wait for confirmation |
| 40-54 | C | Neutral | No clear edge, stay on sidelines |
| 25-39 | D | Caution | Significant headwinds or overvaluation |
| 0-24 | F | Avoid | Major red flags across multiple dimensions |

---

## Sample Output

### `/trade analyze AAPL`

```
╔══════════════════════════════════════════════════════════════╗
║  AI TRADING ANALYSIS                                         ║
║  AAPL — Apple Inc.                                           ║
╚══════════════════════════════════════════════════════════════╝

TRADE SCORE: 74/100 (Grade: A)  Signal: BUY

┌──────────────────────┬───────┬────────┬──────────┐
│ Category             │ Score │ Weight │ Status   │
├──────────────────────┼───────┼────────┼──────────┤
│ Technical Strength   │ 78    │ 25%    │ Strong   │
│ Fundamental Quality  │ 82    │ 25%    │ Strong   │
│ Sentiment & Momentum │ 68    │ 20%    │ Mixed    │
│ Risk Profile         │ 62    │ 15%    │ Mixed    │
│ Thesis Conviction    │ 71    │ 15%    │ Strong   │
└──────────────────────┴───────┴────────┴──────────┘

ENTRY: $178-$182  |  TARGET: $198-$205  |  STOP: $168
RISK/REWARD: 2.8:1  |  POSITION: 3-5% of portfolio

TOP 3 CATALYSTS:
  1. Q3 earnings (Jul 31) — services growth + AI roadmap
  2. iPhone 17 launch (Sep) — AI features as upgrade driver
  3. Margin expansion from services mix shift

Saved: TRADE-ANALYSIS-AAPL.md
```

### `/trade quick NVDA`

```
⚡ TRADE SNAPSHOT — NVDA (NVIDIA Corp.)

  Score: 81/100 (A) — BUY
  Price: $892.40 (+2.3% today)
  Trend: Strong uptrend, above all major MAs

  ✓ Revenue growth +122% YoY (AI demand)
  ✓ RSI 58 — bullish, not overbought
  ✓ Institutional accumulation pattern

  ✗ P/E 65x — premium valuation
  ✗ High beta (1.7) — volatile
  ✗ Concentration risk in AI capex cycle

  Run /trade analyze NVDA for the full multi-agent analysis
```

---

## Use Cases

### Day Traders
Use `/trade technical` for real-time support/resistance levels, indicator readings, and pattern recognition. Run `/trade quick` for fast pre-market scans.

### Swing Traders
Run `/trade analyze` for multi-dimensional analysis. Use `/trade thesis` to build entry/exit plans with specific price levels and timeframes.

### Long-Term Investors
Focus on `/trade fundamental` for deep valuation and moat analysis. Use `/trade compare` to evaluate alternatives. Run `/trade portfolio` for allocation guidance.

### Options Traders
Use `/trade options` for strategy recommendations based on the current setup. Combine with `/trade earnings` for pre-earnings positioning and expected move analysis.

### Portfolio Managers
Run `/trade portfolio` for correlation analysis and rebalancing suggestions. Use `/trade screen` to find new opportunities. Build ranked watchlists with `/trade watchlist`.

### Memory-Aware Researchers
Run `/trade routine` once daily over a Drive-hosted holdings list — it tiers tickers between full analyze and quick snapshot based on prior records, escalates on signal change, and lands a `TRADE-ROUTINE-<ts>.md` delta digest. Use `/trade recall "AAPL bull case"` to cite past analyses with full provenance (`From TRADE-ANALYSIS-AAPL (2026-05-27): _…_`). Add `--cloud` to fan the daily digest out to Slack `#portfolio-updates` + Drive InvestmentSummary.

---

## Installation

### Prerequisites

- **Claude Code** (with an active Anthropic API key)
- **Python 3.8+** (for PDF generation, vector memory, and the routine)
- **reportlab** — `pip3 install reportlab` (for PDF generation only)
- **pinecone + pydantic** — `pip3 install 'pinecone>=7.3,<8' pydantic` (for `/trade routine`, `/trade recall`, and thesis Step-0 memory recall; without these, those features degrade gracefully)

### One-Line Install

```bash
curl -fsSL https://raw.githubusercontent.com/maniksinghvalid/ai-trading-claude/main/install.sh | bash
```

### Manual Install

```bash
git clone https://github.com/maniksinghvalid/ai-trading-claude.git
cd ai-trading-claude
chmod +x install.sh
./install.sh
```

### Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/maniksinghvalid/ai-trading-claude/main/uninstall.sh | bash
```

Or run locally:

```bash
./uninstall.sh
```

The holdings cache at `~/.claude/trade/` (a fallback ticker list, populated the first time you run `/trade holdings` with Drive connected) is intentionally **not** removed by `uninstall.sh`. Delete manually with `rm -rf ~/.claude/trade/` if you also want to wipe it.

---

## Vector Memory (Pinecone)

The slice-3+ routine and recall features write analysis records to a Pinecone vector index so the AI can compound knowledge across sessions: "what did we say about AAPL last month? has the thesis improved or degraded?" Setup is **opt-in** — without it, `/trade analyze`, `/trade quick`, etc. still work fine; only the memory-aware features (`/trade routine`, `/trade recall`, thesis Step-0 recall) degrade gracefully.

### Two transport modes

| Mode | Env vars | When to use |
|---|---|---|
| **Local SDK** | `PINECONE_API_KEY` | Solo / local-only use. The Pinecone Python SDK calls `api.pinecone.io` directly from your laptop. Simplest setup. |
| **Cloud proxy** (Slice 7.5) | `PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN` | Cloud-sandbox sessions (Claude Code Web / scheduled routines) where the local Pinecone key shouldn't ship. The included `proxy/` Vercel Python project fronts Pinecone behind a bearer-token gateway with the API key sandboxed in Vercel env vars. `trade_memory.py` auto-detects both vars and routes through the proxy. See `proxy/README.md` for deployment. |

### Setup steps

1. **Create a Pinecone account and project.** Free tier suffices for personal use (1 GB storage, 2M write units / month, 5M read units / month).
2. **Create the index.** Run `python3 ~/.claude/skills/trade/scripts/trade_memory.py init` after setting `PINECONE_API_KEY`. Creates `trade-reports` integrated-inference index in `aws/us-east-1` (idempotent).
3. **Verify.** `trade_memory.py doctor` reports SDK version, key/proxy presence, index existence, vector count, and embedding-model match. Exits 0 healthy / 1 degraded / 2 unavailable.

### Cost note

Pinecone serverless pricing as of writing: ~$0.10 / 1M reads, ~$2 / 1M writes for storage; integrated-inference embeddings billed at `llama-text-embed-v2` rate (~$0.0001 / 1K tokens). A **20-ticker daily routine** = ~100 vectors/day = 3K/month writes (<$0.01) + ~600 reads/day = 18K/month (<$0.01) + ~1.5M embedding tokens/month (~$0.15). **Expected total: $0.15–$0.30/month for a 20-ticker daily portfolio.** Set a $5/month budget alert in the Pinecone console as a tripwire.

The Vercel proxy adds $0/month on the free tier (well under the 100GB-hr/month + 100K invocation limits for personal use).

### Cloud-routine caveat

The `--cloud` flag on `/trade routine` posts the daily digest to a **hardcoded Slack channel and Drive folder** (`#portfolio-updates` / `InvestmentSummary`). Both destinations are inlined into `skills/trade-routine/SKILL.md`; if your workspace doesn't have them, either create matching destinations and update the skill prose, or pass `--slack-channel <id>` per invocation. The auth model is **research-tool-grade, not production-grade** — token rotation is manual (see `proxy/README.md` → "Rotation procedure"); this is suitable for individual researchers, not regulated production systems.

---

## Project Structure

```
ai-trading-claude/
├── trade/
│   └── SKILL.md                         # Main orchestrator (command router)
├── skills/
│   ├── trade-analyze/SKILL.md           # Full analysis launcher (5-agent fan-out)
│   ├── trade-technical/SKILL.md         # Technical analysis
│   ├── trade-fundamental/SKILL.md       # Fundamental analysis
│   ├── trade-sentiment/SKILL.md         # Sentiment analysis
│   ├── trade-sector/SKILL.md            # Sector rotation
│   ├── trade-compare/SKILL.md           # Stock comparison
│   ├── trade-thesis/SKILL.md            # Investment thesis (Step-0 memory recall)
│   ├── trade-options/SKILL.md           # Options strategies
│   ├── trade-portfolio/SKILL.md         # Portfolio analysis
│   ├── trade-holdings/SKILL.md          # Drive-sourced holdings reader  (Slice 5)
│   ├── trade-routine/SKILL.md           # Tiered portfolio sweep + digest (Slices 6 + 8)
│   ├── trade-recall/SKILL.md            # Cited recall over past reports  (Slice 7)
│   ├── trade-risk/SKILL.md              # Risk assessment
│   ├── trade-screen/SKILL.md            # Stock screener
│   ├── trade-earnings/SKILL.md          # Earnings analysis
│   ├── trade-watchlist/SKILL.md         # Watchlist builder
│   ├── trade-report-pdf/SKILL.md        # PDF report generator
│   └── trade-quick/SKILL.md             # 60-second snapshot
├── agents/
│   ├── trade-technical.md               # Technical analysis agent
│   ├── trade-fundamental.md             # Fundamental analysis agent
│   ├── trade-sentiment.md               # Sentiment analysis agent
│   ├── trade-risk.md                    # Risk assessment agent
│   └── trade-thesis.md                  # Thesis synthesis agent
├── scripts/
│   ├── generate_trade_pdf.py            # PDF generation (ReportLab)
│   ├── trade_memory.py                  # Pinecone CLI (ingest, query, latest, …)
│   ├── trade_scoring.py                 # 6-band score/grade/signal SSOT
│   ├── trade_schemas.py                 # Pydantic schemas + ID + namespace allowlist
│   ├── sync_claude_dir.sh               # Mirror sources into ~/.claude/  (Slice 2)
│   └── sync_proxy_schemas.sh            # Sync trade_schemas → proxy/_lib/  (Slice 7.5)
├── proxy/                               # Vercel HTTPS proxy fronting Pinecone (Slice 7.5)
│   ├── app.py                           # WSGI dispatch entrypoint
│   ├── api/{upsert,query,list,fetch,delete}.py
│   ├── _lib/{auth,validate,ratelimit,pinecone_client,responses,trade_schemas}.py
│   ├── requirements.txt
│   ├── vercel.json
│   └── README.md                        # Deployment + rotation procedures
├── plan/                                # Multi-slice implementation plans
│   ├── portfolio-routine-and-vector-memory.md   # The authoritative plan
│   └── trading-chatbot.md                       # Reference consumer for the schema contract
├── install.sh                           # One-line installer
├── uninstall.sh                         # Clean uninstaller
├── requirements.txt                     # Python dependencies
└── README.md
```

---

## Consumer Integration

> **The Pinecone index is a stable public API.** Downstream tools (web chatbots, dashboards, scheduled briefings, mobile apps) can read the `trade-reports` index directly using a read-only Pinecone key. This section is the contract.

The reference downstream consumer is `plan/trading-chatbot.md` — a separate web-app that talks to the same index. Anything you build that reads `trade-reports` SHOULD validate the contract below on every read and refuse unknown `schema_version` majors.

### Stability rules

- **Field names do NOT change once shipped.** Renaming requires a coordinated upstream migration with a deprecation window.
- **New fields are additive and safe to ship anytime.** Consumers MUST treat unknown fields as opaque pass-through, not error out.
- **The ID scheme is part of the contract** — consumers depend on its lexical sortability for structured queries (`latest`, `timeline`).
- **The 6-band signal labels** (`STRONG BUY` / `BUY` / `HOLD` / `NEUTRAL` / `CAUTION` / `AVOID`) are part of the contract. Label changes require coordinated upstream migration.
- **`schema_version`** (int, currently `1`) is in every record. Consumers SHOULD validate it on read and refuse unknown majors. Increments only on breaking changes (field rename, type change, enum-value removal). Additive changes (new fields, new enum values) do NOT bump it.
- **Read-only consumers connect via a Pinecone "Reader" API key** generated in the Pinecone console (Project → API keys → Reader role). The producer's write key is NEVER shared with consumers.

### ID scheme

```
<TICKER>:<TYPE>:<YYYYMMDD-HHMM>:<section-slug>:<chunk-n>
```

- `<TICKER>` — UPPERCASE ticker, matches `^[A-Z0-9.\-]+$`
- `<TYPE>` — one of `ANALYSIS` / `THESIS` / `TECHNICAL` / `FUNDAMENTAL` / `SENTIMENT` / `RISK` / `EARNINGS` / `QUICK` / `OPTIONS`
- `<YYYYMMDD-HHMM>` — UTC timestamp; sortable lexically
- `<section-slug>` — kebab-cased report section heading (`executive-summary`, `bull-vs-bear`, …)
- `<chunk-n>` — 0-indexed chunk within section when prose exceeds Pinecone's per-record metadata limit (~40 KB, target ~1500 chars/chunk with overlap)

Example: `AAPL:ANALYSIS:20260530-1430:executive-summary:0`

The colon-separated structure lets consumers slice the namespace lexically — e.g., `list` with prefix `AAPL:THESIS:20260530-` returns the chunks of one specific thesis report, no full scan.

### Metadata field table

The full typed surface, mirrored byte-for-byte from `scripts/trade_schemas.py` and verified continuously by gate D.17 in `plan/portfolio-routine-and-vector-memory.md`:

| Field | Type | Always present? | Notes |
|-------|------|-----------------|-------|
| `schema_version` | int | yes | Currently `1`. Increments on breaking changes only. Consumers SHOULD validate on read. |
| `ticker` | string | yes | UPPERCASE; pattern `^[A-Z0-9.\-]+$` |
| `company` | string | yes | Plain company name (mixed case OK) |
| `report_type` | enum | yes | `ANALYSIS` / `THESIS` / `TECHNICAL` / `FUNDAMENTAL` / `SENTIMENT` / `RISK` / `EARNINGS` / `QUICK` / `OPTIONS` |
| `generated_at` | string (ISO-8601) | yes | Full timestamp with tz offset |
| `generated_date` | string (YYYY-MM-DD) | yes | Derived from `generated_at` for date-bucket queries |
| `composite_score` | int (0–100) | ANALYSIS only | null on QUICK / single-dimension reports |
| `technical_score` | int (0–100) | ANALYSIS, TECHNICAL | null otherwise |
| `fundamental_score` | int (0–100) | ANALYSIS, FUNDAMENTAL | null otherwise |
| `sentiment_score` | int (0–100) | ANALYSIS, SENTIMENT | null otherwise |
| `risk_score` | int (0–100) | ANALYSIS, RISK | **INVERTED — higher = safer.** Composes correctly into the weighted total. |
| `thesis_score` | int (0–100) | ANALYSIS, THESIS | null otherwise |
| `iv_rank` | int (0–100) | OPTIONS | Implied-vol rank; null on non-options reports. Additive field (no `schema_version` bump) |
| `strategy_outlook` | enum | OPTIONS | `BULLISH` / `BEARISH` / `NEUTRAL` / `INCOME` / `HEDGE`. Additive |
| `recommended_strategy` | string | OPTIONS | Primary strategy name (free text, e.g. `Covered Call`). Additive |
| `position_bias` | enum | OPTIONS | `LONG` / `FLAT` — holder's stock position that conditioned the strategy. Additive |
| `signal` | enum | when computed | `STRONG BUY` / `BUY` / `HOLD` / `NEUTRAL` / `CAUTION` / `AVOID` — UPPERCASE, exactly 6 values |
| `grade` | enum | when computed | `A+` / `A` / `B` / `C` / `D` / `F` — single-letter only, exactly 6 values |
| `price_at_analysis` | float | when computed | USD |
| `price_target` | float | when computed | USD |
| `stop_loss` | float | when computed | USD |
| `catalysts` | string (comma-joined) | when applicable | Pinecone metadata is flat; lists are joined with `, ` |
| `nearest_catalyst_date` | string (YYYY-MM-DD) | when applicable | null otherwise |
| `run_id` | string | when emitted by routine | Format `routine-<YYYYMMDD-HHMM>-<6hex>`. Null on manual `/trade analyze` invocations. Groups all records from one routine sweep — required for "what changed in last run" queries. |
| `source_path` | string | yes | Original filename for citation rendering (`From TRADE-ANALYSIS-AAPL.md …`) |
| `section` | string | yes | Original Markdown heading (slugified into the ID; preserved here for display) |
| `chunk_index` | int | yes | 0-indexed chunk within section |

Note: Pinecone metadata is **flat scalars only** — no nested objects. Lists are comma-joined into strings (see `catalysts`). Signals and grades are stored UPPERCASE; the README's mixed-case display ("Strong Buy", "Hold") is a presentation choice in the CLI / SKILL.md prose only.

### Score → grade → signal mapping (6-band)

Sourced from `scripts/trade_scoring.py` — the SSOT for this mapping. Mirrors the [Scoring Methodology](#scoring-methodology) table above:

| Score | Grade | Signal |
|-------|-------|--------|
| 85–100 | `A+` | `STRONG BUY` |
| 70–84 | `A` | `BUY` |
| 55–69 | `B` | `HOLD` |
| 40–54 | `C` | `NEUTRAL` |
| 25–39 | `D` | `CAUTION` |
| 0–24 | `F` | `AVOID` |

### Namespace conventions

- **Default namespace:** `trade`. This is where the producer (this tool) writes records and where read-only consumers read from.
- **Per-invocation override:** `trade_memory.py --namespace <NS> <subcommand>` overrides the default for one call. Useful for testing (`--namespace test-ns`).
- **Env var:** `PINECONE_NAMESPACE` sets the default when no flag is supplied. Falls back to `trade` if unset.
- **Consumer-owned namespaces:** downstream consumers MAY use any namespace for their own data (conversation history, user preferences) while **reading from the shared `trade` namespace** for reports. The consumer's namespace is registered in `proxy/_lib/validate.py` `ALLOWED_NAMESPACES` so the proxy boundary accepts writes there too.

### Generating a read-only API key

1. Sign in to https://app.pinecone.io.
2. Open your project → **API keys** in the sidebar.
3. Click **+ Create API key**, name it something the consumer will recognize (e.g., `trading-chatbot-reader`), and select the **Reader** role.
4. Copy the key (you only see it once). Paste it into the consumer's secrets manager (Vercel env, AWS Secrets Manager, etc.) — never commit it.
5. The consumer's Pinecone client connects with this key + the index name `trade-reports`. Reader-role keys can `query`, `fetch`, and `list` but cannot `upsert` or `delete`.

### Reference consumer

See `plan/trading-chatbot.md` — a designed-but-not-yet-built web chatbot that reads `trade-reports` and answers natural-language questions over your ticker history. Its "Upstream contract" section mirrors the field table above; any change to one must update the other in the same commit (gate D.17 verifies the lockstep).

---

## Disclaimer

This tool is for **educational and research purposes only**. It is **NOT financial advice**. It does **NOT** execute trades, manage portfolios, or connect to any brokerage. All analysis is based on publicly available information gathered via web search at the time of the report. Markets are inherently unpredictable. Past performance does not guarantee future results. Always do your own due diligence and consult a licensed financial advisor before making any investment decisions. The creators of this tool accept no liability for any financial losses incurred.

---

<p align="center">
  <strong>Part of the Claude Code Skills Series</strong><br>
  <a href="https://github.com/zubair-trabzada/ai-marketing-claude">AI Marketing Suite</a> ·
  <a href="https://github.com/zubair-trabzada/ai-sales-team-claude">AI Sales Team</a> ·
  <a href="https://github.com/zubair-trabzada/ai-legal-claude">AI Legal Assistant</a> ·
  <a href="https://github.com/zubair-trabzada/ai-reputation-claude">AI Reputation Manager</a> ·
  <a href="https://github.com/zubair-trabzada/geo-seo-claude">GEO/SEO Optimizer</a> ·
  <a href="https://github.com/zubair-trabzada/ai-ads-claude">AI Ads Strategist</a> ·
  <strong>AI Trading Analyst</strong>
</p>

<p align="center">
  <a href="https://skool.com/aiworkshop">Learn How to Build AI Tools with Claude Code</a>
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"/></a>
</p>
