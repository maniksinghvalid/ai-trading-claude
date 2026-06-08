# Codebase Concerns

**Analysis Date:** 2026-06-08

## Tech Debt

### Scoring Weights Duplicated Across 4 Files

**Issue:** The 5 scoring weights and the score→grade→signal conversion table are manually duplicated across multiple files with no central source of truth.

**Files:**
- `README.md` (lines 137-141 for weights, 144-150 for grade/signal table)
- `trade/SKILL.md` (lines 49-55 for weights, 60-67 for grade/signal table)
- `skills/trade-analyze/SKILL.md` (lines 89-95 for weights, agent weight headers are separate)
- `agents/trade-technical.md`, `trade-fundamental.md`, `trade-sentiment.md`, `trade-risk.md`, `trade-thesis.md` (each has a `**Weight:** X%` header)

**Current values (all files in sync):**
- Technical: 25%, Fundamental: 25%, Sentiment: 20%, Risk: 15%, Thesis: 15%
- Grade/Signal: 85+/A+/Strong Buy … 0-24/F/Avoid

**Impact:** If a weight needs updating, all 4+ locations must be manually changed. Current state is in sync, but fragile.

**Fix approach:** Extract weights to `scripts/trade_weights.py` as a module shared by skills/agents, or document a pre-commit gate that validates consistency across files. Immediate fix: create a validation script that checks all files match.

---

### Schema Vendoring Dependency

**Issue:** The Pinecone record schema is the single source of truth at `scripts/trade_schemas.py` but is vendored into the proxy at `proxy/_lib/trade_schemas.py`. Sync must happen via manual script `bash scripts/sync_proxy_schemas.sh` before proxy redeploy.

**Files:**
- `scripts/trade_schemas.py` (SSOT — defines RecordMetadata, enums, validators)
- `proxy/_lib/trade_schemas.py` (vendored copy)
- `scripts/sync_proxy_schemas.sh` (manual sync script)

**Impact:**
- If schema is edited but sync script isn't run, proxy validates against stale schema
- Breaking changes (field rename, type change, enum removal) require coordinated schema_version bump in the model AND explicit consumer migration
- D.17 diff gate enforces the sync but it's still a manual pre-deploy step

**Fix approach:** Automate sync into the proxy deploy pipeline (e.g., pre-deploy GitHub Action that fails if `proxy/_lib/trade_schemas.py` is out of sync with `scripts/trade_schemas.py`). Or make the proxy import from scripts directly (requires proxy to be a submodule or package).

**Current state:** Files are identical (verified via diff); sync is working but not automated.

---

### install.sh / uninstall.sh File List Sync

**Issue:** Both scripts hardcode parallel `SKILLS=()` and `AGENTS=()` arrays. Adding a skill or agent requires updating BOTH scripts.

**Files:**
- `install.sh` (lines 100-119: 18 sub-skills; main orchestrator added separately at line 92)
- `uninstall.sh` (lines 21-41: 19 skills total including main orchestrator)

**Current state:** Arrays are in sync (verified); 19 total skills, 5 agents.

**Impact:** If a skill is added to the repo but not to BOTH arrays:
- install.sh: skill won't be copied to `~/.claude/skills/`
- uninstall.sh: skill won't be removed, leaving stale `~/.claude/skills/<name>/` directory

**Fix approach:** Extract SKILLS/AGENTS lists to a shared `.install.conf` file sourced by both scripts, or use `find` to auto-discover `.md` files in `skills/` and `agents/` directories instead of hardcoding lists. Requires validation that discovered files have proper YAML frontmatter.

---

## Known Bugs

### PDF Generator Silent Demo-Mode Fallback

**Issue:** The PDF generator (`scripts/generate_trade_pdf.py`) runs in **demo mode by default** when called with no arguments or with `--demo` flag. The skill (`skills/trade-report-pdf/SKILL.md`) writes JSON payload to `/tmp/trade_report_data.json` but then invokes the script with no arguments, causing it to ignore the JSON file and render sample data instead.

**Code path:**
- Skill Step 3: writes JSON to `/tmp/trade_report_data.json`
- Skill Step 4: calls `python3 ~/.claude/skills/trade/scripts/generate_trade_pdf.py` (no JSON arg)
- Script lines 791-797: `if len(sys.argv) < 2 or sys.argv[1] == "--demo"` → runs demo mode

**Impact:** User's actual analysis never renders into PDF; sample report is silently generated instead.

**Symptoms:** `TRADE-REPORT.pdf` contains placeholder data (AAPL, NVDA, GOOG) instead of the analysis results.

**Fix approach:** Skill must pass the JSON path as the first CLI argument: `python3 … /tmp/trade_report_data.json TRADE-REPORT.pdf`. Update `skills/trade-report-pdf/SKILL.md` Step 4 to include the file path.

---

## Security Considerations

### Cloud Routines Cannot Hold Secrets

**Issue:** Per state.md and plan/cfg-verification-20260531.md, cloud-routine secret injection (CFG-1) is **BLOCKED**. Anthropic sandboxes don't expose a mechanism to inject secrets into scheduled routines. Workaround: use proxy mode with bearer token in the prompt.

**Files:**
- `plan/cfg-verification-20260531.md` (documents the investigation)
- `state.md` (lines 38-45: CFG-1 BLOCKED impact)

**Current design:**
- Local mode: `PINECONE_API_KEY` set in `.env`, read by scripts
- Cloud mode: `PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN` set in prompt, bearer token not secret-grade

**Risk:** Bearer token in prompt is readable in conversation history. Suitable for research-grade tools; not for regulated/production environments.

**Mitigation:**
- Token rotation is manual (proxy/README.md → "Token hygiene" section)
- Scope: read-only Pinecone operations (query, fetch, list)
- Not suitable for high-value / regulated trading workflows

**Recommendations:**
- Document this limitation in README
- Implement automatic token rotation with short TTLs
- For production: architect cloud routines differently (e.g., separate secret-injection service)

---

### Hardcoded Destination IDs in Skill Prose

**Issue:** Drive folder ID and Slack channel ID are hardcoded in skill definitions with no configuration file support. If the user's workspace doesn't have these exact resources, cloud features fail.

**Files:**
- `skills/trade-routine/SKILL.md` (lines 34-44, 454, 492)
- `skills/trade-holdings/SKILL.md` (lines 33-62, 258-309)

**Hardcoded values:**
- Drive folder: `InvestmentSummary` (id `1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm`)
- Slack channel: `#portfolio-updates` (id `C0B712ARA7M`)

**Impact:**
- If a workspace doesn't have a folder/channel with this ID, cloud routine skips Slack/Drive upload with a warning
- No automatic channel/folder creation; user must create manually or pass `--slack-channel <id>` override (Drive override not supported)
- Changing Drive folder requires editing skill prose, not config

**Current behavior:**
- Slack: `--slack-channel <id>` flag allows override at invocation time
- Drive: no override flag; must edit skill if folder differs

**Fix approach:** 
- Add optional `.env` variables: `TRADE_SLACK_CHANNEL_ID` and `TRADE_DRIVE_ARCHIVE_FOLDER_ID` with skill-prose defaults
- Or add skill flags `--slack-channel` and `--drive-folder` (latter needs implementation)
- Document setup flow: user runs `/trade holdings` which validates both resources and offers creation prompts

---

### Pinecone Metadata Filters Unreliable

**Issue:** Per state.md (lines 83-86), Pinecone's `$eq` and `$in` metadata filters on this index return inconsistent results. A query with `$in` returned 0 hits while `$eq` on the same field returned hits.

**Files:**
- `state.md` (lines 83-86: documented as "gotcha learned")

**Impact:**
- Can't use metadata filtering for verification or downstream queries
- Query → filter → count is non-deterministic
- Affects `/trade recall` and cloud-routine memory verification flows

**Current workaround:** Use deterministic ID-prefix CLI commands instead:
- `latest <T> --type <TYPE>` — fetches by ticker + type, not metadata filter
- `timeline <T>` — lists all records for a ticker, ID-prefix-based

**Risk:** Downstream consumers (trading-chatbot) may try to filter records and get inconsistent results.

**Recommendations:**
- Document this limitation in proxy/README.md
- Provide filter-free query APIs (index_range, list by prefix)
- Contact Pinecone support about index state (may be a bug, may be a config issue)

---

## Performance Bottlenecks

### trade_memory.py Is Large and Slow to Import

**Issue:** `scripts/trade_memory.py` is 1,759 lines with multiple Pinecone operations, Pydantic validation, and retry logic. On first import, it can be slow, especially if Pinecone SDK isn't installed.

**Files:** `scripts/trade_memory.py` (1,759 lines)

**Problem areas:**
- Lines 100-105: `import pinecone` (fails with ImportError if not installed, caught gracefully)
- Pinecone client initialization (lines 165-190): lazy-loads on first use, but repeated calls during a routine can be slow

**Impact:**
- Cloud routines that call `trade_memory.py` multiple times (one per ticker) pay import overhead N times
- Local invocations also pay this cost

**Optimization approach:**
- Split memory operations into a separate service module that can be cached
- Or refactor to lazy-load Pinecone client only when needed (partially done; could be more aggressive)
- Batch upsert operations to reduce API calls (currently one-record-at-a-time; could batch 100s)

---

### Trade-Holdings .xlsm File Unreadable

**Issue:** Default InvestmentSummary master file is `.xlsm` (binary Excel format) which is not natively readable by the skill. It always falls back to `.docx` export.

**Files:**
- `skills/trade-holdings/SKILL.md` (lines 33-87: describes the .xlsm → .docx fallback)

**Current behavior:**
- Tries to read `.xlsm` file via Google Drive MCP (no native parsing capability)
- Falls back to `.docx` export of the same file
- `.docx` may be stale if `.xlsm` hasn't been re-exported recently

**Impact:**
- Holdings read is unreliable if user edits the `.xlsm` master without exporting to `.docx`
- Adds friction: user must manually maintain `.docx` export

**Fix approach:**
- Recommend converting the master InvestmentSummary to a **Google Sheet** (natively readable by Google Drive MCP)
- Or implement `.xlsx` → CSV conversion via a library (openpyxl + Bash pipeline)
- Document the conversion process in README

---

## Fragile Areas

### Trade-Analyze Fan-Out (5 Parallel Agents)

**Issue:** The flagship `/trade analyze` launches 5 subagents in parallel (technical, fundamental, sentiment, risk, thesis). If any agent times out or returns malformed scoring, the entire analysis fails.

**Files:**
- `skills/trade-analyze/SKILL.md` (lines 39-95: orchestration logic)
- `agents/trade-*.md` (5 agents, each with complex scoring logic)

**Why fragile:**
- No timeout handling per-agent; one slow agent blocks synthesis
- Agent response parsing assumes exact formatting (Markdown header structure); typos → parsing failure
- Scoring bounds validation is loose (relies on agent discipline to stay 0-100)

**Safe modification approach:**
- Add explicit timeout per agent (5 min max)
- Validate agent response structure before synthesis (check for required headers)
- Add score bounds-checking in synthesis (clamp 0-100, warn on out-of-range)
- Test coverage: run each agent standalone to verify response format

---

### Trade-Routine Escalation Logic

**Issue:** The routine implements tiered escalation: quick → analyze on signal change. The logic is complex (recommend-tier, signal comparison, escalation gate).

**Files:**
- `skills/trade-routine/SKILL.md` (lines 200-300: escalation decision logic)

**Fragile points:**
- `recommend-tier` decision tree (lines 220-240) has multiple edge cases (null prior, no quick result, signal mismatch)
- Escalation cap (default 10, recently changed to 30) gates options overlay — if cap is too low, options deferred
- No validation that escalated analysis actually has a different signal before writing report

**Safe modification:**
- Document the decision tree explicitly (state → action map)
- Add logging/tracing at each decision point
- Validate that escalation produced a different signal before committing
- Test with edge cases: no prior analysis, signal tie, deferred options

**Test coverage gap:** No tests for the escalation decision tree with various ticker histories.

---

### Pinecone Record Schema Validation

**Issue:** Pydantic schema in `scripts/trade_schemas.py` uses `extra="forbid"`, meaning any extra field in a record causes validation failure. This is strict but fragile if producers add debugging fields or consumers forget to strip fields.

**Files:**
- `scripts/trade_schemas.py` (line 146: `extra="forbid"`)
- `proxy/_lib/validate.py` (re-validates at proxy boundary)

**Impact:**
- Skill writes a debugging field → ingest fails
- Proxy gets a record with an unknown field → 422 validation error
- Cloud routine's options overlay defers due to validation error

**Risk:** Silent failures; validation errors are logged but not surfaced to user.

**Recommendation:**
- Keep `extra="forbid"` for production but add a `--lenient` mode for development
- Add debug logging that lists rejected fields (helps troubleshoot schema mismatches)

---

## Scaling Limits

### Cloud Routine Context/Token Budget

**Issue:** A single cloud routine session can't hold 10+ `/trade analyze` (5-agent fan-out) PLUS 10+ `/trade options` analyses. Per state.md, the first combined run deferred the options overlay because the session ran out of budget.

**Files:**
- `state.md` (lines 46-58: describes the deferred options issue)
- `skills/trade-routine/SKILL.md` (line 27: `--max-escalations` flag added as mitigation)
- `skills/trade-options/SKILL.md` (position+signal-aware strategy matrix)

**Current mitigation:** Decouple options into a separate scheduled job (`trade-options-sweep`, triggered daily at 15:00 UTC).

**Scaling limitations:**
- Single routine can analyze ~10-14 holdings before hitting context limits
- Multi-agent analysis consumes ~30-50k tokens per ticker
- Each options analysis adds ~10-20k tokens

**Recommendations:**
- Continue the decoupled job approach (options sweep separate from analyze routine)
- Monitor token usage; if portfolio grows >20 holdings, consider batching sweeps (e.g., analyze stocks A-M, options N-Z)
- Add `--batch-size N` flag to cap tickers per routine invocation

---

### PDF Generator Memory Usage

**Issue:** `scripts/generate_trade_pdf.py` loads all TRADE-*.md files into memory before rendering. For large portfolios with 20+ reports, memory usage can spike.

**Files:** `scripts/generate_trade_pdf.py` (lines 790-811: main logic)

**Current behavior:** Loads entire JSON payload, renders to PDF in one go.

**Scaling limit:** ~50-100 reports before memory becomes an issue (reportlab creates in-memory page objects).

**Recommendation:** Stream PDF generation report-by-report instead of loading all at once; or implement pagination (PDF generation already splits into sections).

---

## Test Coverage Gaps

**[Untested area]:** No unit tests exist for:
- Scoring calculations (weights, composite formula)
- Pinecone record validation (all 9 ReportType variants, OPTIONS fields)
- PDF generation (parsing markdown, extracting data, rendering)
- trade_memory.py operations (upsert, query, delete, timeline)
- Skill orchestration (command routing, subprocess calls)

**Files:** Project-wide; no `tests/` directory, no `.test.py` files.

**Risk:** 
- Silent failures in complex skills (trade-analyze agent orchestration, trade-routine escalation)
- Scoring weights calculated incorrectly; bug goes unnoticed for weeks
- PDF generator silently produces corrupted output
- Pinecone schema changes cause validation to fail in production

**Priority:** High (especially for scoring calculations and Pinecone record schema).

**Recommendation:**
- Add `pytest` fixtures for scoring calculations
- Add integration tests for Pinecone (with mock or local Pinecone instance)
- Add PDF generation tests (render sample data, verify PDF structure)
- Gate on test pass + coverage >80% before merge

---

## Missing Critical Features

### No Configuration File Support

**Issue:** Hardcoded values (Drive folder ID, Slack channel ID, max escalations, etc.) are embedded in skill prose. No `.env` or config file structure exists to override them.

**Impact:** User customization requires editing Markdown skill files (no support for it in the tool's design).

**Files:** All skills; especially `trade-routine/SKILL.md`, `trade-holdings/SKILL.md`.

**Recommendation:** Add optional env var support:
- `TRADE_SLACK_CHANNEL_ID` (default: `C0B712ARA7M`)
- `TRADE_DRIVE_ARCHIVE_FOLDER_ID` (default: `1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm`)
- `TRADE_MAX_ESCALATIONS` (default: 30)
- `TRADE_MAX_OPTIONS` (default: bounded by escalation cap)

---

### No Brokerage Integration

**Issue:** Tool is research-only; does not connect to brokerages, execute trades, or manage money. This is by design (educational tool), but limits real-world usage.

**Impact:** Analyses can't be acted on automatically; user must manually execute trades based on recommendations.

**Mitigation:** Tool is clear about this in disclaimers. Not a bug, but a scope limitation to note.

---

## Dependencies at Risk

### Pinecone Python SDK Version Pinning

**Issue:** `install.sh` checks for `pinecone` but doesn't specify a version constraint.

**Files:** `install.sh` (lines 196-204: checks for pinecone + pydantic but no version pin)

**Current: install.sh` (lines 196-204):**
```bash
if python3 -c "import pinecone, pydantic" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} pinecone + pydantic installed"
```

No version constraints. Plan mentions `pinecone>=7.3,<8` but installer doesn't enforce it.

**Risk:** Major version bumps (Pinecone 8.x, 9.x) may change client API, breaking scripts.

**Recommendation:** Update install.sh to specify version range:
```bash
pip3 install 'pinecone>=7.3,<8' pydantic
```

---

### reportlab Dependency

**Issue:** PDF generation requires `reportlab` but it's not listed in a `requirements.txt`.

**Files:**
- `scripts/generate_trade_pdf.py` (lines 22-32: ImportError fallback)
- `install.sh` (lines 188-194: checks for reportlab)
- `README.md` and CLAUDE.md mention `pip3 install reportlab`

**Current state:** Manual install; no lockfile.

**Risk:** Different users may install different versions; PDF rendering may vary.

**Recommendation:** Add `requirements.txt` with pinned versions:
```
reportlab==3.6.8
pinecone>=7.3,<8
pydantic>=2.0,<3
```

---

## Architectural Constraints

### No Offline Mode (Beyond Holdings Cache)

**Issue:** Tool requires WebSearch/WebFetch for all analyses (no local data). Holdings cache (`TRADE-HOLDINGS.md`) is the only offline fallback.

**Impact:** If network is down or WebSearch quota is exhausted, `/trade analyze` fails.

**Mitigation:** TRADE-HOLDINGS.md caching allows `/trade routine` to fall back to quick snapshot if Drive is unavailable.

**Recommendation:** Document network requirements explicitly; clarify quota limits (WebSearch max requests/day).

---

## Cross-Cutting Concerns

### State.md Contains Open Questions

**Issue:** state.md (lines 90-102) lists unresolved validation questions about the options-sweep feature.

**Key open:** Was the `trade-options-sweep` job validation successful? Background poll `bl88l7c17` may have confirmed OPTIONS records landed, but this hasn't been reported.

**Impact:** Feature may have succeeded silently or failed silently; needs explicit confirmation.

**Recommendation:** Implement post-deploy verification: after routine completes, explicitly check for OPTIONS records:
```bash
python3 scripts/trade_memory.py latest AAPL --type OPTIONS
```
and report presence/absence to Slack.

---

### Options-Sweep Cadence Not Tuned

**Issue:** `trade-options-sweep` is hardcoded to run daily at 15:00 UTC (state.md line 67). This may be too frequent (waste) or too infrequent (stale data) depending on usage.

**Impact:** Intraday traders may want more frequent options data (every 2h during market hours). Long-term holders may be fine with daily.

**Recommendation:** Make cadence configurable:
- `TRADE_OPTIONS_CADENCE` env var (default: `0 15 * * *`)
- Document market-hours cadence: `0 14,16,18 * * MON-FRI` (0900, 1100, 1300 ET on trading days)

---

### Version Bump Ceremonies Not Automated

**Issue:** Schema breaking changes require:
1. Bump `SCHEMA_VERSION` in `scripts/trade_schemas.py`
2. Run `bash scripts/sync_proxy_schemas.sh`
3. Redeploy proxy
4. Coordinate with downstream consumers (trading-chatbot, dashboards)

**Files:** `scripts/trade_schemas.py`, `proxy/_lib/trade_schemas.py`, proxy deployment.

**Risk:** Any step skipped breaks producer/consumer contract.

**Recommendation:** Automate via GitHub Actions:
- Check on schema changes: trigger a workflow that verifies sync + creates a PR to proxy
- Require PR approval before proxy deploy
- Notify consumers (via issue/email) of breaking changes

---

*Concerns audit: 2026-06-08*
