# Plan: Portfolio Routines + Pinecone Memory + Thesis Recall

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** make `ai-trading-claude` accumulate value over time — sweep portfolio tickers on a
schedule, persist every report into a durable vector index, and surface prior analysis when
building new theses — and make all of this work in a Claude cloud-scheduled routine, not just
locally.

**Architecture:** cloud-first. Pinecone (serverless, integrated inference) is the durable
report index. Google Drive (via the connected MCP) is the source-of-truth for the holdings
list and the durable archive of generated reports. A new Python CLI
(`scripts/trade_memory.py`) is the only memory-layer executable; new skills are pure-prose
orchestrators that call it via Bash. Shared scoring logic lives in `scripts/trade_scoring.py`
so neither the PDF generator nor the memory engine depends on the other. The cloud-routine
surface is the reference target; local-interactive is the same code path with stdout output
instead of Slack/Drive output.

**Tech Stack:** Markdown prompts (skills + agents) + Python 3 (`pinecone>=5`, `reportlab` for
PDF). MCP connectors used: Google Drive (required), Slack (cloud-output, optional), Gmail
(cloud-output, optional).

---

## Strategic shifts (third-pass)

This is the third revision of the plan. The first revision applied an architectural review.
The second revision reoriented to cloud-first. This revision (third) folds in the third-pass
review's critical findings — most importantly the `.claude/agents/` data-loss landmine, the
internally-inconsistent CFG degraded-mode descriptions, and the "WATCH" label that didn't
exist in the codebase.

Changes from the prior revision:

1. **`sync_claude_dir.sh` no longer uses `--delete` on agents.** The repo's `.claude/agents/`
   already contains 7 non-trade agents (`code-refactorer`, `code-reviewer`,
   `git-commit-helper`, `product-strategy-advisor`, `senior-code-reviewer`, `staff-engineer`,
   `system-architect`) that do not exist at the root. The original `rsync -a --delete` would
   have wiped them on first install. The skills rsync still uses `--delete` (skills mirror is
   authoritative); agents rsync is additive only.
2. **`recommend-tier` returns `NEUTRAL` (the existing label), not `WATCH` (invented).** The
   6-band table aligns to `trade/SKILL.md:62`'s existing labels: STRONG BUY / BUY / HOLD /
   NEUTRAL / CAUTION / AVOID. README's duplicate-"Caution" bug (currently maps both 40-54 and
   25-39 to "Caution") is fixed in slice 1 as part of the same reconciliation.
3. **Scoring helpers extracted to `scripts/trade_scoring.py`.** Both `generate_trade_pdf.py`
   and `trade_memory.py` import from it. Removes the cross-script import fragility of
   "memory imports from PDF generator."
4. **CFG verification moved to slice 0** (½ day, runs before any code). If CFG-1 fails
   permanently, slice 8 is permanently blocked and slices 1–7 should be reframed as
   local-confirmed rather than cloud-aspiring.
5. **Slice 3 split into 3a + 3b.** 3a is `VectorStore` + `init` + `ingest` + `query` (gates
   on real Pinecone). 3b is `recommend-tier` + `timeline` + `rebuild` + `delete` + `doctor`.
6. **Degraded-mode table rewritten.** The prior version was internally inconsistent
   (CFG-1 fail → "tiering only" requires Pinecone which needs the secret). The new table
   accurately describes what works under each CFG failure combination.
7. **Escalation decision matrix made explicit.** Plan now defines exactly what "quick signal
   differs from stored signal" means, including the null-prior case and what happens to the
   already-written quick file.
8. **First-run flows added** for `TRADE_DRIVE_ARCHIVE_FOLDER_ID` (via `doctor` and `ingest`)
   and for `--slack-channel <id>` (via `slack_search_users`).
9. **`trade-portfolio` ↔ `trade-holdings` overlap addressed.** Slice 5 also updates
   `trade-portfolio` to try Drive first, fall back to interactive paste — no silent failure.
10. **Drive subfolder creation, `rebuild` from Drive folder, quick frontmatter subset**
    specified in §1 and §2 respectively.
11. **`TRADE-HOLDINGS.md` reinstated as a fallback tier** (not the primary). If Drive is
    unavailable, the routine reads the last successful local copy rather than aborting. Drive
    is still re-read every sweep when available.
12. **Six new quality gates** (D.11–D.16) covering the new fix surface.

**Consumer-readiness additions (fourth-pass, folded in to support `plan/trading-chatbot.md`):**

13. **`PINECONE_NAMESPACE` promoted to a top-level `--namespace NS` CLI flag** on
    `trade_memory.py`. Lets downstream consumers operate in per-user namespaces without
    process restart while reading the shared `trade` namespace for reports. Env var
    continues to work as the default.
14. **Consumer Integration contract** documented in `README.md` and `CLAUDE.md`. Declares
    the Pinecone metadata schema as a stable public API so external consumers (the
    trading-chatbot, dashboards, briefing services) can build against it. Field names
    cannot change silently; new fields are additive; removals or renames require a
    coordinated upstream change.
15. **Two new quality gates** (D.17 schema-contract currency, D.18 `--namespace` flag
    end-to-end).

---

## Confirmed product decisions (unchanged)

- Holdings list lives in **Google Drive**, read via the connected Drive MCP connector.
- Vector store is **Pinecone serverless with integrated inference** (Pinecone hosts the
  embedding model `llama-text-embed-v2` — no separate embedding key, no local model).
- Depth is **tiered**: cheap `/trade quick` snapshot by default; escalate to full 5-agent
  `/trade analyze` only on signal-change / catalyst-proximity / staleness.
- Trigger surface includes **on-demand local** and **Claude cloud routine** via `/schedule`.

> **Setup tradeoff:** Pinecone is managed cloud. This introduces a `PINECONE_API_KEY` + network
> dependency and a Pinecone account; the plugin is no longer fully offline/no-key for the memory
> layer. In exchange, the index persists across machines and across cloud sandbox sessions —
> the only durable state survives even when the local FS is wiped.

---

## Architecture overview

```
                              ┌─────────────────────────────────────────────┐
                              │ Pinecone (cloud, serverless, integrated     │
                              │  inference) — index: trade-reports          │
                              │  • one record per report SECTION (chunk)    │
                              │  • id: <TICKER>:<TYPE>:<YYYYMMDD-HHMM>:…    │
                              │  • metadata: scores, signal, dates, run_id  │
                              └──────────────────▲──────────────────────────┘
                                                 │ upsert / query (server-side embed)
                                                 │
Google Drive ──────────────────► /trade routine  │
  holdings.csv (or Sheet)        (orchestrator)  │
  (primary source of truth)             │        │
   ├ fallback: ~/.claude/trade/         ▼        │
   │   TRADE-HOLDINGS.md      trade_memory.py recommend-tier <T>
   │                                    │
   │                    ┌───────────────┴────────────────┐
   │                    │                                │
   │                    ▼                                ▼
   │            /trade quick <T>             /trade analyze <T>
   │            (stdout, no file)            (5 parallel agents,
   │                    │                     writes TRADE-ANALYSIS-<T>.md)
   │                    │                                │
   │           routine assembles                         │
   │           TRADE-QUICK-<T>-<ts>.md                   │
   │                    │                                │
   │                    └──► escalation check ◄──────────┘
   │                         (signal change vs latest stored)
   │                                  │
   │                                  ▼
   │                trade_memory.py ingest <f> ──► Pinecone
   │                                  │
   │                                  └──► Drive archive
   │                                       (AI Trading/Reports/<TICKER>/)
   │
   └► All execution surfaces share the same data path.
     Output routing differs only in WHO reads it.

                  Routine digest TRADE-ROUTINE-<ts>.md
                  ├─ local: stdout + CWD file
                  └─ cloud: stdout + CWD file + Slack DM + Drive upload

/trade recall "<q>" [ticker]  ──► trade_memory.py query  ──► Pinecone search
/trade thesis <T>             ──► Step 0 reads memory before fresh research
```

**Structured queries without similarity search:** the ID scheme
`<TICKER>:<TYPE>:<YYYYMMDD-HHMM>:…` is lexically sortable by recency. `latest <ticker>` uses
Pinecone `list(prefix="<TICKER>:ANALYSIS:")`, walks pagination, takes the lexically-largest
timestamp, and `fetch`es the record's metadata — no query vector needed. `recommend-tier`
consumes that metadata and applies the tiering rules. `timeline` is bounded by `--since` /
`--limit` defaults (last 12 months, max 50 runs).

---

## Cloud-first deployment model

Three execution surfaces. They use the same skills and the same CLI; only outputs differ.

| Surface | Trigger | Holdings source | Digest output | Report archive |
|---------|---------|-----------------|---------------|----------------|
| **Cloud routine** (reference) | `/schedule` cron | Drive MCP (attached connector) | Slack DM + Drive upload + CWD file | Drive archive (Drive MCP) + Pinecone |
| **Local interactive** | user runs `/trade routine` | Drive MCP → fallback `TRADE-HOLDINGS.md` | stdout + CWD file | Drive archive (Drive MCP) + Pinecone |
| **Local cron** (legacy) | macOS `cron` running `claude -p` | Drive MCP → fallback `TRADE-HOLDINGS.md` | CWD file | Drive archive + Pinecone |

The routine's behavior split is driven by one flag the prompt sets: `--cloud`. The routine
skill prompt for a cloud routine reads `/trade routine --cloud --slack-channel <id>`;
locally a user types `/trade routine`. The skill prose handles both — no separate skill.

---

## Cloud feasibility gates (slice 0 — run before any code)

These are **verification steps**, not design questions. Run them as one-shot
`/schedule` routines. Each gate must come back green before slice 8 (cloud deployment) is
implemented; slices 1–7 can proceed in parallel based on their own gates regardless of the
CFG outcomes.

**CFG-1 — Secret injection.** Create a one-shot routine that runs:
```bash
echo "PINECONE_API_KEY length: ${#PINECONE_API_KEY}; first 4 chars: ${PINECONE_API_KEY:0:4}"
```
**Gate:** the routine log shows non-zero length and `pcsk` prefix. Discover where to set the
secret in the claude.ai routines UI before scheduling (likely at the environment level under
https://claude.ai/code/routines). If no UI mechanism exists, slice 8 is blocked permanently
(or until Anthropic ships one); slices 1–7 still ship and provide full local value.

**CFG-2 — WebSearch + WebFetch in cloud `allowed_tools`.** Create a one-shot routine with
`allowed_tools: ["Bash", "Read", "Write", "Edit", "Glob", "Grep", "WebSearch", "WebFetch"]`
that prints the result of `WebFetch https://example.com`.
**Gate:** routine completes; example.com content visible in logs.

**CFG-3 — Subagent dispatch (`Task` tool) in cloud `allowed_tools`.** Create a one-shot
routine with `Task` added to `allowed_tools` that dispatches a trivial subagent that returns
"OK".
**Gate:** routine log shows subagent output.

Slice 0 produces a written verification report at `plan/cfg-verification-<YYYYMMDD>.md` with
one line per gate: `PASS|FAIL|BLOCKED` + the routine ID + the log snippet that justifies the
outcome.

---

## Files to CREATE

| Path | Purpose |
|------|---------|
| `scripts/trade_scoring.py` | Shared `score_grade()` + `trade_signal()` helpers. Imported by both `generate_trade_pdf.py` and `trade_memory.py`. Single source of truth for the 6-band table. |
| `scripts/trade_memory.py` | Standalone CLI memory engine over Pinecone, including the `recommend-tier` decision and Drive archive helpers |
| `scripts/sync_claude_dir.sh` | Shell script mirroring `skills/` and `trade/` into `.claude/skills/` and additively syncing `agents/` into `.claude/agents/` (no `--delete` on agents, see §3) |
| `.claude/skills/<19 skills>/SKILL.md` | Mirror so cloud sandboxes auto-discover (generated by `scripts/sync_claude_dir.sh`; committed to Git) |
| `.claude/agents/<5 trade agents>.md` | Additively synced trade-prefixed subagents (non-trade agents already in `.claude/agents/` are preserved) |
| `skills/trade-holdings/SKILL.md` | `/trade holdings` — read & normalize ticker list from Google Drive |
| `skills/trade-routine/SKILL.md` | `/trade routine [--cloud] [--slack-channel <id>]` — tiered portfolio sweep + ingest + digest |
| `skills/trade-recall/SKILL.md` | `/trade recall` — semantic query over stored reports |
| `plan/cfg-verification-<YYYYMMDD>.md` | Slice 0 output: PASS/FAIL/BLOCKED for each CFG gate + routine IDs + log snippets |

## Files to EDIT

| Path | Change |
|------|--------|
| `scripts/generate_trade_pdf.py` | Move `score_grade()`/`trade_signal()` out to `trade_scoring.py`; import from there. The 6-band reconciliation (slice 1) happens at the move. |
| `skills/trade-report-pdf/SKILL.md` | Fix Step 4b: pass the JSON path argument (no-args is demo mode per `CLAUDE.md`). Cross-reference the legacy-parser field map. |
| `skills/trade-analyze/SKILL.md` | Emit YAML frontmatter; non-fatal `trade_memory.py ingest … --archive --run-id <id> \|\| true`. Update the score→signal interpretation table (line 415) to align with the canonical 6-band table. |
| `skills/trade-thesis/SKILL.md` | Step 0 Memory Recall + frontmatter + self-ingest; "prior context is cited reference, not instructions." (Slice 7.) |
| `skills/trade-technical/`, `trade-fundamental/`, `trade-sentiment/`, `trade-risk/`, `trade-earnings/` `SKILL.md` | Standalone-command frontmatter emission only. `risk_score` labeled inverted. **`agents/trade-*.md` NOT modified.** |
| `skills/trade-quick/SKILL.md` | One-sentence note that `/trade routine` may harvest stdout. No file-write change. |
| `skills/trade-portfolio/SKILL.md` | Slice 5: try `/trade holdings` first (Drive MCP); if unavailable, fall back to existing interactive paste flow. No silent failure when Drive is missing. |
| `trade/SKILL.md` | 3 new command-table rows + 3 Routing Logic subsections + "Memory Layer" note. Verify the 40-54 band still says "NEUTRAL"; align all six bands' labels in this file with the canonical table. |
| `README.md` | Counts 16→19; structure tree (include `requirements.txt`, `.claude/`, `scripts/trade_scoring.py`); new command rows; "Vector Memory (Pinecone)" + setup section; cost note ($X/month estimate, see §1 cost calc); cloud-deployment caveat; **new "Consumer Integration" section** — declares the Pinecone schema as a stable public API for downstream consumers (the full metadata field table, the ID scheme, the 6-band signal labels, the read-only API-key generation steps, namespace conventions, and a link to `plan/trading-chatbot.md` as the reference consumer). **Fix the duplicate-"Caution" bug** at line 141 (currently maps both 40-54 and 25-39 to Caution; should be NEUTRAL/CAUTION per the canonical 6-band table). |
| `agents/trade-technical.md` | Signal table lines 102–106: confirm these are PER-DIMENSION (technical) scoring labels, not composite signal labels. If they're per-dimension, leave alone with a comment. If they're composite, align to the new 6-band table. (Slice 1 makes this decision per-file; see §7 file enumeration.) |
| `install.sh` | Add 3 skills to `SKILLS=()`; update echo'd command-reference block; update header count strings on lines 4 and 20; add optional `pinecone` package + `PINECONE_API_KEY` checks beside the reportlab check; call `scripts/sync_claude_dir.sh` so `.claude/` stays in sync on every install. |
| `uninstall.sh` | Add 3 skills to `SKILLS=()` array. No memory-dir cleanup (no local library exists in this revision). |
| `requirements.txt` | Add `pinecone>=5` (commented as optional for memory/recall). Listed in README's project tree. |
| `CLAUDE.md` | Document memory layer; frontmatter contract; 3 new commands; `trade_memory.py` as a second executable; `trade_scoring.py` as the single source of truth for `score_grade`/`trade_signal`; UPPERCASE signal/grade in metadata; `.claude/` mirror discipline; the cloud dependency; **the Consumer Integration contract** — one-paragraph note that the Pinecone metadata schema is a stable public API for downstream consumers (link to `plan/trading-chatbot.md` as the reference consumer; rule: field renames require coordinated upstream migration). |

---

## 1. `scripts/trade_memory.py` — the memory engine

Standalone CLI invoked via Bash. Imports `score_grade()` / `trade_signal()` from a sibling
`trade_scoring.py` (NOT from `generate_trade_pdf.py` — see §3 import resolution). All
Pinecone-specific calls live in a `class VectorStore` so the store is swappable later.

**Config (env):**

| Var | Default | Purpose |
|-----|---------|---------|
| `PINECONE_API_KEY` | *(required)* | All vector ops |
| `PINECONE_INDEX` | `trade-reports` | Index name |
| `PINECONE_EMBED_MODEL` | `llama-text-embed-v2` | Integrated-inference model |
| `PINECONE_CLOUD` | `aws` | Serverless cloud |
| `PINECONE_REGION` | `us-east-1` | Serverless region |
| `PINECONE_NAMESPACE` | `trade` | Default namespace; also overridable per-invocation via the top-level `--namespace NS` flag (see Subcommands). Lets downstream consumers operate in per-user namespaces without changing env. |
| `TRADE_DRIVE_ARCHIVE_FOLDER_ID` | *(optional)* | Drive folder ID for report archive; if unset, `--archive` is a no-op + warning |

**Top-level flags** (apply to every subcommand):
- `--namespace NS` — overrides `PINECONE_NAMESPACE` for this invocation. Use for
  per-user / per-portfolio isolation by downstream consumers (e.g., the trading-chatbot
  storing per-user state) without restarting the process. Falls back to the env var, then
  to `trade`.

**Subcommands:**

```
init
    Create serverless index via create_index_for_model if absent (idempotent).
    Records the embedding model name in the index spec.

ingest <report.md> [--archive] [--run-id ID]
    Parse one report → upsert section records.
    --archive: also upload to <archive>/<TICKER>/<filename>. Subfolder creation flow:
        1. search_files(name="<TICKER>", parent=<archive>, mimeType="folder")
        2. if not found, create_file(name="<TICKER>", parent=<archive>, mimeType="folder")
        3. create_file(name=<basename>, parent=<TICKER-folder-id>, contents=<file>)
    First-run UX: if --archive is passed but TRADE_DRIVE_ARCHIVE_FOLDER_ID is unset,
    emit one-line setup message: 'export TRADE_DRIVE_ARCHIVE_FOLDER_ID=<id>; create a
    Drive folder via /trade holdings or directly in Drive and paste the ID here.'

query "<text>" [--ticker T] [--type TYPE] [--since YYYY-MM-DD] [-n 5]
    Pinecone semantic search + metadata filter.

latest <ticker> [--type TYPE]
    list-by-prefix + fetch → newest record's metadata as JSON.
    Walks pagination explicitly (default page-size; loops until empty).

timeline <ticker> [--since YYYY-MM-DD] [--limit N]
    All records for ticker, oldest→newest.
    Defaults: --since now-12mo, --limit 50.

list [--ticker T] [--type TYPE] [--limit N]
    Manifest listing. Default --limit 100.

delete --ticker T [--before YYYY-MM-DD] [--yes]
    GC for tickers that left the portfolio. Confirms unless --yes.

rebuild <source> [--exclude-ticker T,T2,...]
    Re-ingest every TRADE-*.md under <source>.
    <source>: local dir (starts with "/" or "~") OR Drive folder ID.
    Drive flow: list_files_in_folder(folder_id) → for each markdown file,
        download_file_content → ingest in-process → log progress.
    --exclude-ticker: don't ingest these tickers (e.g., tickers that left the portfolio).

recommend-tier <ticker>
    Apply tiering rules to the latest metadata and print one of:
      analyze   no prior ANALYSIS, OR catalyst within 14 days,
                OR last full analysis > 30 days old, OR Pinecone unavailable
      quick     otherwise
    Exits 0 on success. If Pinecone is unavailable, prints "analyze" (safe default)
    AND exits 0 with a stderr warning — the routine treats this as "tier known, memory
    unknown" and proceeds.
    Signal-change escalation happens AFTER quick runs and lives in the routine skill
    (see §5 routine, escalation matrix).

doctor
    Reports: SDK availability, API-key presence, index existence + vector count,
    index embedding model vs PINECONE_EMBED_MODEL (warns on drift),
    Drive MCP availability (best-effort),
    TRADE_DRIVE_ARCHIVE_FOLDER_ID set+valid (warns with setup hint if unset).
    Exit codes: 0 healthy, 1 degraded, 2 unavailable.
```

**Record schema:** chunk per report section (split on `##`; cap ~1500 chars w/ overlap;
Pinecone metadata limit ~40 KB/record). `id = <TICKER>:<TYPE>:<YYYYMMDD-HHMM>:<section-slug>:<n>`.
Single namespace `trade`. Metadata (flat scalars; lists comma-joined; **signal/grade UPPERCASE**):
`ticker, company, report_type, generated_at, generated_date, composite_score, technical_score,
fundamental_score, sentiment_score, risk_score (INVERTED — higher=safer), thesis_score, signal,
grade, price_at_analysis, price_target, stop_loss, catalysts, nearest_catalyst_date, run_id,
source_path, section, chunk_index` + chunk text.

**Drive archive:** when `--archive` is passed and `TRADE_DRIVE_ARCHIVE_FOLDER_ID` is set, the
report is uploaded to `<folder>/<TICKER>/TRADE-<TYPE>-<TICKER>-<YYYYMMDD-HHMM>.md` using the
subfolder-creation flow above. Failures are warnings, not errors — Pinecone upsert is
authoritative.

**Cost ceiling (concrete):** Pinecone serverless pricing as of writing: ~$0.10/1M reads,
~$2/1M writes for storage; integrated-inference embeddings billed separately at the model's
hosted-inference rate. A 20-ticker daily routine ≈ 100 vectors written/day = 3K/month
(<$0.01/month writes); reads dominated by `recommend-tier` + `latest` = ~600/day = 18K/month
(<$0.01/month reads). Embedding cost is the variable: at ~$0.0001 per 1K tokens (
`llama-text-embed-v2` typical), 100 chunks/day × 500 tokens × 30 = 1.5M tokens/month ≈
$0.15/month. **Total expected: $0.15–$0.30/month for a 20-ticker daily portfolio.** Document
in README; set a monthly budget alert at $5 in the Pinecone console.

**Robustness:** wrap `from pinecone import Pinecone` in try/except; check `PINECONE_API_KEY`;
vector subcommands exit with a clear single-line message + non-zero if either is missing.
Skills always call `ingest … --archive --run-id <id> || true` so memory failure never aborts
an analysis or routine. Reports with no frontmatter still upsert prose chunks with
filename-derived metadata + a warning. `recommend-tier` specifically does NOT exit non-zero
on Pinecone failure — it prints `analyze` and exits 0 so the routine continues with a safe
default.

**Consumer integration contract** (the Pinecone index as a public API): the metadata schema
above is a **stable public contract** for downstream consumers — the trading-chatbot in
`plan/trading-chatbot.md`, and any future dashboard, mobile app, or scheduled briefing
service. Stability rules:

- Field names do NOT change once shipped. Renaming requires a coordinated upstream
  migration with a deprecation window.
- New fields are additive and safe to ship anytime; consumers must treat unknown fields
  as opaque pass-through, not error out.
- The ID scheme `<TICKER>:<TYPE>:<YYYYMMDD-HHMM>:<section-slug>:<n>` is part of the
  contract — consumers depend on its lexical sortability for structured queries (`latest`,
  `timeline`).
- The 6-band signal labels (STRONG BUY / BUY / HOLD / NEUTRAL / CAUTION / AVOID) are part
  of the contract; label changes require coordinated upstream migration.
- Read-only consumers connect via a Pinecone "Reader" API key generated in the Pinecone
  console (Project → API keys → Reader role). The producer's write key is NEVER shared.
- Consumers may use any namespace for their own data (e.g., conversation history) while
  reading from the shared `trade` namespace for reports. See `--namespace` flag above.

Any plan touching field names, the ID scheme, or signal labels must update both the schema
docs in `README.md`/`CLAUDE.md` AND notify downstream consumers (the trading-chatbot is the
first one). See `plan/trading-chatbot.md` § "Upstream contract" for the consumer's view of
this contract.

## 2. Report self-description (frontmatter) + fallback parser

Going forward, every **standalone analysis skill** (not `agents/*.md`) emits a YAML frontmatter
block above its existing markdown body:

```yaml
---
trade_report: true
ticker: AAPL
company: Apple Inc.
report_type: ANALYSIS        # ANALYSIS|THESIS|TECHNICAL|FUNDAMENTAL|SENTIMENT|RISK|EARNINGS|QUICK
generated_at: 2026-05-30T14:30:00-07:00
composite_score: 74          # ANALYSIS only; omit when N/A
technical_score: 78
fundamental_score: 82
sentiment_score: 68
risk_score: 62               # INVERTED — higher = lower risk
thesis_score: 71
signal: BUY                  # UPPERCASE; one of STRONG BUY|BUY|HOLD|NEUTRAL|CAUTION|AVOID
grade: A
price_at_analysis: 185.40
price_target: 200.00
stop_loss: 168.00
catalysts: ["Q3 earnings 2026-07-31", "iPhone 17 launch 2026-09"]
nearest_catalyst_date: 2026-07-31
---
```

**Field availability by report_type** (which fields are valid where):

| Field | ANALYSIS | THESIS | TECHNICAL | FUNDAMENTAL | SENTIMENT | RISK | EARNINGS | QUICK |
|-------|----------|--------|-----------|-------------|-----------|------|----------|-------|
| `composite_score` | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `technical_score` | ✓ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `fundamental_score` | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ |
| `sentiment_score` | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| `risk_score` | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `thesis_score` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `signal`, `grade` | ✓ | ✓ (thesis-derived) | ✓ (per-dim) | ✓ (per-dim) | ✓ (per-dim) | ✓ (per-dim) | ✗ | ✓ |
| `price_at_analysis` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `price_target`, `stop_loss` | ✓ | ✓ | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ |
| `catalysts`, `nearest_catalyst_date` | ✓ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ |

Skills populate only fields they computed. `trade_memory.py` does not enforce required fields;
missing values are stored as `null`. `latest --type QUICK` returns null for `composite_score`
without error.

**Fallback parser** `_parse_legacy()` handles frontmatter-less reports (reuse the
field-extraction map from `skills/trade-report-pdf/SKILL.md` Step 2). Ingest logic:
**frontmatter → else legacy parser → else filename-only**. Legacy-extracted `signal`/`grade`
are uppercased before storage.

## 3. Skill discovery in cloud (`.claude/skills/` mirror)

Cloud sandboxes get a fresh `git clone` of the repo. They do not run `install.sh`. Claude
Code auto-discovers skills from `.claude/skills/<name>/SKILL.md` inside a checked-out repo.
The current repo layout puts skills at `skills/<name>/SKILL.md` (root); cloud sandboxes won't
find them there.

**Decision: rsync-mirror, not symlinks.** Symlinks committed to Git are viable on macOS/Linux
but break on Windows clients and on `curl|bash`-style flat installs that some plugin
distribution channels use. Rsync produces real files that survive any transport. Symlinks were
evaluated and rejected for portability.

**Decision: drop `--delete` on `.claude/agents/` rsync.** The repo's `.claude/agents/`
contains 7 non-trade agents at the time of writing (see strategic-shifts §1). The skills
rsync stays authoritative (`--delete` keeps the mirror clean), but the agents rsync is
additive only. Drift risk on agents: a trade agent renamed at the root won't have its old
mirror removed automatically — this is acceptable because subagent definition files are rare
to rename, and `install.sh` could be extended to nuke `.claude/agents/trade-*.md` before the
agents rsync if precision is needed later.

`scripts/sync_claude_dir.sh`:

```bash
#!/usr/bin/env bash
# Mirror skills/ + trade/ → .claude/skills/ (authoritative; uses --delete).
# Additively sync agents/ → .claude/agents/ (non-trade agents preserved; no --delete).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mkdir -p "$ROOT/.claude/skills" "$ROOT/.claude/agents"
rsync -a --delete "$ROOT/skills/"  "$ROOT/.claude/skills/"
rsync -a          "$ROOT/agents/"  "$ROOT/.claude/agents/"
rsync -a --delete "$ROOT/trade/"   "$ROOT/.claude/skills/trade/"
echo "synced .claude/ from skills/, agents/ (additive), trade/"
```

`install.sh` calls this script as its first step. `CLAUDE.md` documents "re-run this script
after editing any skill or agent" as a contributor convention. Quality gate D.10 verifies
no drift at any commit.

## 4. Output routing for `/trade routine`

The routine prompt accepts `--cloud` and `--slack-channel <id>` flags. Behavior:

| Output | Local | Local + Slack | Cloud routine |
|--------|-------|----------------|---------------|
| stdout | always | always | always (visible in routine logs) |
| `TRADE-ROUTINE-<ts>.md` in CWD | always | always | always (ephemeral in cloud, but visible in logs) |
| Slack DM with digest | only if `--slack-channel` given | yes | yes (channel from routine prompt) |
| Drive upload of digest | only if `TRADE_DRIVE_ARCHIVE_FOLDER_ID` set | yes | yes |
| Per-ticker report Drive archive | yes (via `ingest --archive`) | yes | yes |

In cloud mode, the digest message to Slack is posted via `slack_send_message` (or
`slack_create_canvas` for longer digests). Failure to deliver to Slack is a warning, not an
error; Drive upload is the durability backstop.

**Slack channel discovery (one-time setup for cloud routines):** the user runs `/trade
setup` (folded into slice 5's `/trade holdings` workflow): the skill calls
`slack_search_users` with the user's email (already in MEMORY.md), gets the user ID, opens
a DM with `slack_get_thread` or the equivalent IM API, and prints the channel ID. The user
pastes it into the routine prompt when creating the cloud routine. No persisted config —
the channel ID is hardcoded into the routine prompt at schedule-creation time.

## 5. New skills

### `/trade holdings`

Drive MCP `search_files` for a holdings/portfolio file → `read_file_content` (handles Sheets &
Docs natively) → normalize to a clean uppercase ticker list (strip shares/$/names; allow
`BRK.B`-style dots; de-dup).

**First-run flow:**
- If no holdings file found in Drive, offer to `create_file` a starter holdings Sheet on
  confirmation.
- Also offer to create the report archive folder (`AI Trading/Reports/`) and print the
  resulting folder ID with a one-liner: `export
  TRADE_DRIVE_ARCHIVE_FOLDER_ID=<id>`.
- Also offer to look up the Slack DM channel ID via `slack_search_users` (using the email
  from MEMORY.md) and print it for the user to use in a future `/schedule` call.

**Output:**
- Print normalized list.
- Write CWD `TRADE-HOLDINGS.md` (for visibility, no longer load-bearing).
- Write `~/.claude/trade/TRADE-HOLDINGS.md` as the **fallback cache** for the routine to use
  when Drive is unavailable. This is the only piece of local state.

`/trade routine` always re-reads Drive directly when Drive is available; the cache is read
only on Drive failure.

### `/trade routine [--cloud] [--slack-channel <id>]`

Trigger-agnostic orchestration:

1. Generate `run_id = routine-<YYYYMMDD-HHMM>-<6hex>` (Bash: `date +%Y%m%d-%H%M` +
   `openssl rand -hex 3`; the skill prompt also handles environments where `openssl` is
   unavailable by falling back to `head -c 24 /dev/urandom | xxd -p`).
2. Read holdings:
   - Primary: Drive MCP `search_files` + `read_file_content`.
   - Fallback: `~/.claude/trade/TRADE-HOLDINGS.md` if Drive is unavailable; print a
     `[warn] Drive unavailable; using cached holdings from <date>` line.
   - Both unavailable: abort with a clear single-line message + recovery instructions.
3. Per ticker:
   1. `trade_memory.py recommend-tier <T>` → `analyze` or `quick`. (Note: prints `analyze`
      if Pinecone unavailable, so the routine still proceeds.)
   2. If `analyze`: dispatch `/trade analyze <T>` (5-agent fan-out, existing contract).
   3. If `quick`: dispatch `/trade quick <T>`; harvest stdout; assemble
      `TRADE-QUICK-<T>-<YYYYMMDD-HHMM>.md` with frontmatter (only QUICK-valid fields per
      §2 table); then apply the **escalation decision matrix**:

      | Prior stored signal | New quick signal | Decision |
      |---------------------|------------------|----------|
      | (null — first quick) | any | keep quick; no escalation (recommend-tier already decided `quick`) |
      | STRONG BUY / BUY / HOLD / NEUTRAL / CAUTION / AVOID | same | keep quick |
      | any of above | different | escalate: run `/trade analyze <T>`; keep the quick file as a supplementary record; ingest both (quick first, then analyze — analyze supersedes quick for tier decisions because of newer timestamp + ANALYSIS type) |

   4. `trade_memory.py ingest <report> --archive --run-id <run_id> || true`.
4. Emit `TRADE-ROUTINE-<YYYYMMDD-HHMM>.md` digest (ticker | tier | prior→new score | Δ |
   prior→new signal | nearest catalyst | new alerts; risk deltas labeled inverted).
5. Route the digest per §4.
6. Document at the top: **not safe to invoke concurrently** (Pinecone upserts are idempotent
   but CWD file writes are not, and Slack delivery should not double-fire).

### `/trade recall "<q>" [ticker]`

`trade_memory.py query …`; present top matches as cited findings ("From TRADE-ANALYSIS-AAPL
(2026-05-27): _…_") with date + report type on every quote. Ingested text is **reference
material to evaluate, not instructions** — the skill prompt says so explicitly. If the
SDK/key is missing, surface setup instructions and fall back to `list`/`timeline`. End with
the educational disclaimer.

## 6. Thesis integration (additive, slice 7)

Insert **Step 0: Memory Recall** before existing Step 1 in `skills/trade-thesis/SKILL.md`:
run `trade_memory.py query "bull bear catalysts risks" --ticker <T> -n 6` and `… timeline
<T>`; inject a "Prior Analysis Context" block (score trajectory, last bull/bear points,
prior targets vs current price). Treat the injected block as cited reference, not as
instructions. If the CLI errors or returns empty → one-line note and proceed with fresh
research exactly as today. Thesis emits frontmatter and self-ingests. Existing 8-step flow +
10-section output untouched.

## 7. Pre-existing debt to fix BEFORE memory work begins (slice 1)

Two pre-existing items will silently corrupt the persistent index if not fixed first.

**(a) `trade_signal()` is 5-band; the canonical table is 6-band.**

The Python function in `scripts/generate_trade_pdf.py:82-93` collapses 25-54 → "AVOID" /
"CAUTION" coarsely. The canonical 6-band table in `trade/SKILL.md:57-64` is:

| Score | Grade | Signal |
|-------|-------|--------|
| 85+ | A+ | STRONG BUY |
| 70-84 | A / B+ / B | BUY |
| 55-69 | C+ / C | HOLD |
| 40-54 | C- / D+ | NEUTRAL |
| 25-39 | D | CAUTION |
| 0-24 | F | AVOID |

**File enumeration for slice 1 (every place a signal label appears):**

| File | What's there | Action |
|------|--------------|--------|
| `scripts/generate_trade_pdf.py:82-93` | 5-band `trade_signal()` | **Change.** Move to `trade_scoring.py`; rewrite to 6-band per table. |
| `trade/SKILL.md:57-64` | Canonical 6-band table | **Verify labels match exactly** (STRONG BUY / BUY / HOLD / NEUTRAL / CAUTION / AVOID). If `trade/SKILL.md` says "Neutral" mixed-case, normalize to UPPERCASE in the metadata storage but keep the human-readable case in the prose table. |
| `skills/trade-analyze/SKILL.md:415` | Interpretation table | **Change** to align with canonical 6-band. |
| `README.md:141` | Has "Caution" duplicated across 40-54 and 25-39 | **Fix the duplicate-Caution bug.** Map 40-54 → NEUTRAL, 25-39 → CAUTION. |
| `agents/trade-technical.md:102-106` | Per-dimension technical signal table on 5-band 80/65/50/35/0 boundaries | **Leave alone.** Add a comment noting this is per-dimension (technical only), not composite. The composite table is in `trade-analyze/SKILL.md`. |
| `agents/trade-fundamental.md`, `agents/trade-sentiment.md`, `agents/trade-risk.md`, `agents/trade-thesis.md` | Per-dimension scoring tables | **Verify per-dimension only.** Add comments noting they don't represent composite signals. No label changes unless they explicitly use a composite-style signal value. |

**Slice 1 gate (replaces the previous shorter version):**
1. `trade_scoring.py` exists with `score_grade()` + `trade_signal()` matching the canonical
   6-band table.
2. `generate_trade_pdf.py` imports from `trade_scoring.py`; running
   `python3 scripts/generate_trade_pdf.py` (demo) produces correct labels.
3. The 6 boundary scores (85/70/55/40/25/0) routed through both helpers produce STRONG
   BUY/BUY/HOLD/NEUTRAL/CAUTION/AVOID exactly.
4. `README.md` no longer has the duplicate-Caution bug; greps for "Caution" + "NEUTRAL"
   appear in the expected bands.
5. `agents/*.md` per-dimension tables are annotated (comments added) so a future contributor
   doesn't assume they're composite.

**(b) PDF generator no-args bug.**

`skills/trade-report-pdf/SKILL.md` Step 4b instructs running `generate_trade_pdf.py` with no
arguments — but no-args is demo mode (per `CLAUDE.md`). Fix the prompt to pass the JSON path.
Same skill is the documented source for the legacy parser's field map.

## 8. Rollout slice order

Each slice ships independently; each gate must pass before the next. Slice 0 unblocks
slice 8 only (slices 1–7 proceed in parallel regardless of CFG outcomes).

### Slice 0 — CFG verification routines (½ day, runs first)
Create the three one-shot `/schedule` routines (CFG-1/2/3 per §"Cloud feasibility gates").
Document outcomes in `plan/cfg-verification-<YYYYMMDD>.md`. If CFG-1 fails permanently, mark
slice 8 as BLOCKED in the plan and reframe slices 1–7 in `README.md` as "local + opportunistic
cloud" rather than "cloud-first."

**Gate:** all three CFG routines have run; outcomes file committed; slice 8 blockers (if any)
documented.

### Slice 1 — Pre-existing debt (1–2 days)
- Extract `score_grade()`/`trade_signal()` to `scripts/trade_scoring.py`.
- Reconcile to 6-band using NEUTRAL (not WATCH).
- Fix `trade-report-pdf` no-args invocation in `skills/trade-report-pdf/SKILL.md`.
- Apply all file changes per §7 enumeration.
- Annotate per-dimension `agents/*.md` tables so they don't get aligned by mistake later.

**Gate:** §7 slice-1 gate 1–5 pass; `grep -rn "Caution\|Neutral\|WATCH"` across the repo
returns only intentional uses; the duplicate-Caution bug in `README.md:141` is gone.

### Slice 2 — `.claude/` mirror + sync script (½ day)
- Write `scripts/sync_claude_dir.sh` per §3 (drops `--delete` on agents rsync).
- **Pre-flight:** `ls .claude/agents/` and document the 7 non-trade agents currently there
  (commit the list as `plan/.claude-preflight-<YYYYMMDD>.md`).
- Run the sync script.
- Verify the 7 non-trade agents are still present in `.claude/agents/` after sync.
- Commit `.claude/skills/` + `.claude/agents/` (with the new trade agents merged in but
  non-trade preserved).

**Gate:** `ls .claude/agents/ | wc -l` ≥ pre-flight count + 5 (5 trade agents); all 7
non-trade agents are byte-identical to their pre-sync state; `diff -rq skills/
.claude/skills/<root-subset>/` shows no drift.

### Slice 3a — `trade_memory.py` core (2–3 days)
- Implement `class VectorStore` (Pinecone wrapper).
- `init`, `ingest`, `query` subcommands.
- Frontmatter parser + `_parse_legacy()` fallback.

**Gate:** Verification A.1–A.6 below pass on a sample file; `init` is idempotent; ingest
records are visible in Pinecone via `query`.

### Slice 3b — `trade_memory.py` higher-level commands (2–3 days)
- `recommend-tier`, `timeline`, `list`, `rebuild`, `delete`, `doctor`.
- Drive archive helper (subfolder creation flow).
- `rebuild` from Drive folder ID.
- **Top-level `--namespace NS` flag** plumbed through argparse so every subcommand
  honors it; falls back to `PINECONE_NAMESPACE` env var, then to `trade`. (Supports the
  trading-chatbot's per-user namespace pattern without process restart.)
- All commands respect the import-resolution pattern in §3 import resolution below.

**Gate:** Verification A.7–A.10 pass; `recommend-tier` returns `analyze` for fresh ticker,
`analyze` for ticker with catalyst within 14 days, `quick` for fresh ANALYSIS without
catalyst; `recommend-tier` with unset key returns `analyze` and exit 0 (not crash);
`trade_memory.py --namespace test-ns list` queries only the `test-ns` namespace, leaving
the default namespace untouched.

### Slice 4 — Frontmatter rollout for standalone skills (2–3 days)
Edit 7 standalone `SKILL.md` files + `trade-analyze`. **Do NOT touch `agents/trade-*.md`.**
Add non-fatal `ingest --archive` to `trade-analyze`. Re-run `sync_claude_dir.sh` and commit.

**Gate:** `/trade analyze AAPL` → frontmatter parses → `trade_memory.py ingest` → `latest
AAPL` returns the record with all populated fields non-null; frontmatter-field-availability
table from §2 is enforced.

### Slice 5 — `trade-holdings` skill + `trade-portfolio` Drive-first update (1–2 days)
- `trade-holdings`: Drive read, CWD copy, `~/.claude/trade/TRADE-HOLDINGS.md` fallback cache.
- `trade-portfolio`: try `/trade holdings` first; fall back to interactive paste.
- First-run flow: starter Sheet, archive-folder creation, Slack channel discovery.
- Add to install/uninstall arrays and `trade/SKILL.md` command table.
- Run sync script.

**Gate:** `/trade holdings` produces a normalized list; missing-Drive case prompts to create a
starter sheet; `/trade portfolio` without Drive falls back to interactive (no silent failure);
fallback cache exists at `~/.claude/trade/TRADE-HOLDINGS.md` after first run.

### Slice 6 — `trade-routine` skill (3–5 days, local-only first)
Tiered sweep using `recommend-tier`; quick-snapshot file written by the routine;
minute-granularity digest; `run_id` generation; re-reads Drive every sweep with cache
fallback. **Escalation decision matrix from §5 implemented in skill prose.** No `--cloud`
flag wiring yet (output goes to stdout + CWD). Run sync script.

**Gate:** cold local run forces full analyze per ticker; second run uses quick tier for
tickers without catalyst proximity; signal-change in a quick correctly escalates to analyze
and both records appear in Pinecone; `timeline <T>` shows QUICK followed by ANALYSIS at the
escalation timestamp.

### Slice 7 — `trade-recall` + thesis Step-0 (2–3 days)
Recall as a thin wrapper over `trade_memory.py query` with cited output format and
prompt-injection caveat. Thesis Step-0 prepended; Prior Analysis Context block present when
records exist; "treat as reference" framing. Run sync script.

**Gate:** every quoted chunk in `/trade recall` carries source filename + date + report type;
`/trade thesis AAPL` produces structurally identical output with and without Pinecone
configured (only the Prior Analysis Context block differs).

### Slice 8 — Cloud routine deployment (2–3 days, after CFG verifications pass)
Add the `--cloud` flag wiring + Slack DM delivery + Drive archive upload. Document the
cloud routine creation flow in `README.md`. Document the verification routines so the user
can re-run them on Anthropic platform changes.

**Gate:** create a one-shot cloud routine via `/schedule` that runs `/trade routine --cloud
--slack-channel <id>` against a 2-ticker holdings list; routine completes; Pinecone shows
new records; Slack receives the digest; Drive folder shows uploaded files.

### Slice 9 — Docs + install polish (1 day)
`CLAUDE.md`; `README.md` (counts 16→19, structure tree, Pinecone setup, cloud caveat, cost
note); `install.sh` Pinecone advisories; `install.sh` banner string updates (lines 4, 20);
confirm `uninstall.sh`. **Author the new "Consumer Integration" section in `README.md`**:
full metadata field table (mirrors §1 record schema), ID scheme spec, 6-band signal label
list, read-only Pinecone key generation steps, namespace conventions
(`PINECONE_NAMESPACE`/`--namespace`), link to `plan/trading-chatbot.md` as the reference
consumer. **Mirror a one-paragraph summary into `CLAUDE.md`** so contributors know the
schema is a public contract before editing field names.

**Gate:** fresh `./install.sh` from a clean home directory installs 19 skills, syncs
`.claude/`, prints Pinecone advisories when SDK or key are missing; `./uninstall.sh` removes
everything it installed; the Consumer Integration section in `README.md` is present and
its metadata table matches the actual fields stored by `trade_memory.py ingest` (verified
by ingesting a sample report and diffing the field names — see D.17).

---

## §3 import resolution (between `trade_memory.py` and `trade_scoring.py`)

Both scripts are installed into `~/.claude/skills/trade/scripts/` by `install.sh` and also
exist at `scripts/` in a cloud-sandbox checkout. The import must work in both contexts.

**Pattern:** `trade_memory.py` resolves `trade_scoring.py` by file location:

```python
# at top of trade_memory.py
import importlib.util, pathlib, sys
_here = pathlib.Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("trade_scoring", _here / "trade_scoring.py")
trade_scoring = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trade_scoring)
score_grade = trade_scoring.score_grade
trade_signal = trade_scoring.trade_signal
```

This avoids assuming `trade_scoring.py` is on `sys.path` or that the current working
directory contains it. Works whether invoked as `python3 scripts/trade_memory.py …` from the
repo root or `~/.claude/skills/trade/scripts/trade_memory.py …` from anywhere.

`generate_trade_pdf.py` uses the same pattern. Both scripts continue to be runnable as
standalone CLIs.

---

## Verification

### A. CLI-level (fastest, gates for slices 3a/3b)

1. `export PINECONE_API_KEY=…` then `python3 scripts/trade_memory.py doctor` → reports SDK +
   key present, index existence, vector count, embedding-model match. Exit 0.
2. `trade_memory.py init` → creates `trade-reports` integrated-inference index in
   `aws/us-east-1` (idempotent).
3. Write a sample `TRADE-ANALYSIS-TEST.md` with frontmatter → `ingest …` → doctor count rises.
4. `ingest --archive …` (with `TRADE_DRIVE_ARCHIVE_FOLDER_ID` set) → file appears in Drive
   folder under `<archive>/TEST/`; subfolder creation succeeded on first run; second ingest
   reuses the same `TEST/` subfolder (no duplicate).
5. `latest TEST --type ANALYSIS` → JSON with composite_score/signal (UPPERCASE).
   `timeline TEST` → ordered rows.
6. `query "bull case" --ticker TEST` → returns the matched section.
7. Legacy path: ingest a frontmatter-less report → fallback parser populates ticker/type/date.
8. `recommend-tier TEST` after a fresh TEST ingest → prints `quick`. With a catalyst within
   14 days seeded in the metadata → prints `analyze`. With Pinecone unavailable
   (`PINECONE_API_KEY=invalid`) → prints `analyze` AND exits 0.
9. `delete --ticker TEST --yes` → all TEST records removed; `latest TEST` returns empty.
10. `rebuild <drive-folder-id>` → after a fresh `delete`, records reappear in Pinecone;
    `rebuild <drive-folder-id> --exclude-ticker TEST` → records do NOT reappear for TEST.

### B. Local end-to-end (gates for slices 5–7)

1. Confirm 3 new skills land in `~/.claude/skills/` after `./install.sh` and `trade_memory.py`
   + `trade_scoring.py` in `~/.claude/skills/trade/scripts/`.
2. Put a 2–3 ticker holdings Sheet in Drive → `/trade holdings` → normalized list + CWD copy +
   `~/.claude/trade/TRADE-HOLDINGS.md` cache.
3. `/trade routine` cold → first run forces full analyze per ticker; records upserted; Drive
   folder receives copies; `TRADE-ROUTINE-<ts>.md` produced.
4. `/trade routine` again → tickers take quick tier; digest shows deltas; `TRADE-QUICK-<T>-
   <ts>.md` files produced by the routine.
5. Force a signal-change scenario (manually edit a stored signal in Pinecone or seed a
   contrarian fixture); rerun `/trade routine` → tickers with changed signals escalate to
   analyze; `timeline <T>` shows QUICK followed by ANALYSIS.
6. `/trade recall "bull case for AAPL"` → cited results with date + type.
7. `/trade thesis AAPL` → Step 0 injects prior context; thesis self-ingests.
8. **Drive-failure path:** disconnect the Drive MCP (or rename the holdings file in Drive);
   `/trade routine` → falls back to `~/.claude/trade/TRADE-HOLDINGS.md`; warns about stale
   data; still completes.
9. **Pinecone-failure path:** unset `PINECONE_API_KEY` → `/trade recall` and `/trade thesis`
   degrade gracefully ("memory disabled"); `/trade routine` runs all tickers at `analyze`
   tier (recommend-tier safe default); analyze still completes (ingest is `|| true`).

### C. Cloud end-to-end (gates for slice 8)

1. CFG-1: secret-injection verification routine completes; `PINECONE_API_KEY` length non-zero.
2. CFG-2: WebSearch + WebFetch routine completes; example.com fetch succeeds.
3. CFG-3: subagent dispatch routine completes; trivial subagent returns.
4. Real one-shot routine: `/trade routine --cloud --slack-channel <id>` against a 2-ticker
   holdings list → routine completes; Pinecone has new records; Slack receives the digest;
   Drive folder has uploaded files.
5. Recurring routine: schedule the same prompt to run hourly for 4 hours; confirm 4 successful
   runs, no duplicate records, digest deltas reflect lack of price change.

### D. Quality gates (continuous; checked at each slice)

1. `trade_memory.py doctor` exit codes are exact (0/1/2) per the three states.
2. Score-table parity: 6 boundary scores routed through `score_grade()` + `trade_signal()`
   match `trade/SKILL.md` exactly. Labels are STRONG BUY / BUY / HOLD / NEUTRAL / CAUTION /
   AVOID (no "WATCH" anywhere).
3. Frontmatter round-trip: every field a skill claims to populate (per §2 availability
   table) is non-`None` in `latest`; fields the skill type doesn't compute are `null`.
4. Legacy parity: a frontmatter-less report yields populated `composite_score`, `signal`,
   `grade`, `ticker`, `generated_date`.
5. Non-fatal isolation: invalid `PINECONE_API_KEY` → `/trade analyze` still produces a
   correct `TRADE-ANALYSIS-<T>.md`.
6. Idempotent routine: two back-to-back routines produce identical Pinecone state (no
   duplicate IDs); digest shows "no delta" for all tickers.
7. Install banner consistency: `ls ~/.claude/skills/ | wc -l` equals the number printed by
   the `install.sh` banner.
8. Recall citation format: every quote carries `From TRADE-<TYPE>-<TICKER> (<YYYY-MM-DD>):
   "…"`.
9. Thesis Step-0 is additive only: structurally identical 10-section output with and without
   Pinecone; only the "Prior Analysis Context" block differs.
10. `.claude/` mirror is current: `diff -rq skills/ .claude/skills/<root-subset>/` shows no
    drift; `diff -rq agents/trade-*.md .claude/agents/` shows the 5 trade agents present and
    byte-identical.
11. **`sync_claude_dir.sh` is non-destructive on agents.** Run twice; verify all non-trade
    agents in `.claude/agents/` are unchanged byte-for-byte (`md5sum -c` against a
    pre-flight checksum file).
12. **`recommend-tier` graceful failure.** Invalid `PINECONE_API_KEY` → `recommend-tier
    AAPL` prints `analyze` and exits 0; `/trade routine` proceeds without crashing and the
    digest notes "memory unavailable; defaulted to full analyze."
13. **Drive subfolder idempotence.** Two consecutive `ingest --archive` for the same ticker
    → exactly one `<TICKER>/` subfolder in Drive; the second file lives alongside the first
    inside that subfolder.
14. **Cross-script import works from any CWD.** `cd /tmp && python3 ~/.claude/skills/trade/
    scripts/trade_memory.py doctor` resolves `trade_scoring.py` without `ImportError`.
15. **Quick frontmatter subset.** Ingest a `TRADE-QUICK-*.md`; `latest <T> --type QUICK`
    returns a record with `signal` populated, `composite_score=null`, no errors.
16. **`trade-portfolio` Drive-first fallback.** Without Drive configured, `/trade portfolio`
    prompts for manual input (does not silently exit).
17. **Consumer schema contract is current.** The metadata field table in `README.md`'s
    Consumer Integration section matches the actual fields stored by `trade_memory.py
    ingest`. Verify by ingesting a sample report, listing the record's metadata keys via
    `trade_memory.py latest <T>`, and diffing against the documented table — no drift
    allowed. Run on every commit that touches `scripts/trade_memory.py` or skill frontmatter.
18. **`--namespace` flag works end-to-end.** `trade_memory.py --namespace test-ns list`
    queries only `test-ns`; default-namespace queries are unaffected.  The flag overrides
    `PINECONE_NAMESPACE` env when both are set.

---

## Risks

- **`sync_claude_dir.sh` could still drift if a contributor forgets to re-run it.** The
  rsync runs on every `./install.sh`, but not automatically on commits (no pre-commit
  framework in the repo). Mitigation: D.10 gate; CLAUDE.md "re-run sync after editing"
  reminder; cloud routines that hit a stale `.claude/skills/` produce wrong output silently
  — accept this as a contributor-discipline risk for now.
- **Cloud secret-injection mechanism may not exist (CFG-1).** Slice 0 establishes the truth
  before slices 1–7 land; if it fails, slice 8 is blocked but slices 1–7 still ship full
  local value.
- **WebSearch / WebFetch may be denied in cloud (CFG-2).** Cloud routines degrade to
  Pinecone-only operations: `recommend-tier` + `latest` + Slack notification of "stored
  signals as of <ts>; run /trade routine locally for fresh analysis." Still useful as a
  scheduled reminder.
- **Subagent dispatch may be denied in cloud (CFG-3).** Cloud routines run quick-tier only.
  `/trade analyze` cannot run in cloud; the routine escalates to "run locally" Slack
  notification when escalation conditions are met.
- **CFG-1 + CFG-2 both fail.** Routine runs in cloud as a heartbeat: "memory and web both
  unavailable; cloud routine can only confirm the schedule is alive." Notify Slack with that
  exact text. Document this is the minimum useful cloud mode.
- **Drive MCP authorization can lapse.** Routine falls back to
  `~/.claude/trade/TRADE-HOLDINGS.md`; if cloud, the cache may not exist, so the routine
  aborts with a clear message. Mitigation: contributor runs `/trade holdings` locally
  periodically to refresh the cache; document this maintenance step.
- **Pinecone SDK drift.** `pinecone` SDK and integrated-inference API have evolved; confirm
  exact call shapes at implementation time via Context7.
- **Embedding-model drift silently breaks search.** `doctor` warns on mismatch. Migration
  path: change env, reset index, `rebuild <drive-folder-id>`.
- **Metadata 40 KB/record limit.** Chunk per section with a char cap.
- **Drive archive failures don't block ingestion.** Pinecone upsert is authoritative.
- **Legacy parser brittleness.** Keys off stable score-table cells; frontmatter rollout
  makes new reports lossless.
- **`risk_score` inversion.** Labeled `(inverted)` everywhere it surfaces.
- **Quick signal vs composite score.** Composite-delta trigger dropped; signal-change is the
  sole quick-tier escalation trigger per the §5 escalation matrix.
- **Pinecone cost.** ~$0.15–$0.30/month for 20-ticker daily; set Pinecone-console budget
  alert at $5; document in README.
- **Pre-existing debt.** Slice 1 fixes it before any data lands.
- **Routine concurrency.** Documented as unsafe; minute-granularity digest + idempotent
  upserts limit damage.
- **Prompt-injection in ingested text.** Cited sources + Step-0 framing.
- **Stale records when a ticker leaves holdings.** `trade_memory.py delete --ticker T`
  covers manual GC; `rebuild --exclude-ticker T,…` keeps the deletion sticky across rebuilds.
- **`.claude/agents/` data loss avoided** (this risk was real in the prior revision — fixed
  by dropping `--delete` on the agents rsync per §3).

---

## Long-term maintenance shape

This plan commits the project to a four-dependency maintenance surface:

1. **Pinecone SDK** evolution. `doctor` + `trade_scoring.py` extraction reduce blast radius.
2. **Google Drive MCP** connector stability. Lapse handled by local cache fallback; cache
   refresh is a manual contributor task.
3. **Slack MCP** connector stability. Only affects cloud digest delivery; Drive upload is
   the durability backstop.
4. **`.claude/` mirror discipline.** No pre-commit hook means contributor diligence is the
   only defense against drift. Quality gates D.10 + D.11 detect it on install/test runs.

Recovery playbook: if Drive is unavailable for an extended period, the local
`~/.claude/trade/TRADE-HOLDINGS.md` keeps the routine running for the last-known holdings;
Pinecone retains all stored reports across the gap; `rebuild` from any Drive backup restores
the index if Pinecone is wiped. The system is single-point-of-failure-free for short
outages of any one dependency.

---

## Self-review checklist

- [x] **Spec coverage:** Drive holdings (§5), Pinecone storage (§1), tiering decision (§1
  `recommend-tier`), routine sweep (§5 + escalation matrix), recall (§5), thesis Step-0
  (§6), cloud deployment (§§3-4 + slice 8), pre-existing debt (§7), CFG verification (§Cloud
  feasibility gates + slice 0).
- [x] **No placeholders:** every subcommand has a defined input/output; every file edit
  describes the change; every gate has a runnable check; cost ceiling has concrete numbers.
- [x] **Type consistency:** `recommend-tier` returns `analyze|quick`; signal values are
  STRONG BUY / BUY / HOLD / NEUTRAL / CAUTION / AVOID everywhere (no "WATCH"); frontmatter
  field availability is type-gated per §2 table.
- [x] **Cross-file contract scan:** 6-band signal table appears in §7 (debt enumeration),
  §1 (cost calc), §2 (frontmatter spec), §verification (D.2), and is referenced in §1
  (`trade_scoring.py` import).
- [x] **Critical landmines from prior reviews resolved:** `sync_claude_dir.sh` no longer
  destroys non-trade agents (§3); degraded-mode descriptions are internally consistent
  (§Risks); "WATCH" replaced with "NEUTRAL" throughout; `trade_scoring.py` extraction
  eliminates the cross-script import fragility.
