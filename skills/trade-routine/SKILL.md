---
name: trade-routine
description: Portfolio routine — tiered daily sweep over the user's holdings, dispatching /trade analyze or /trade quick per ticker based on `trade_memory.py recommend-tier`, escalating quicks on signal change, and emitting a TRADE-ROUTINE digest with a per-ticker delta table.
---

# Portfolio Routine

You are the routine orchestrator for the AI Trading Analyst system. When the
user runs `/trade routine`, you perform a **tiered sweep** over every ticker
in their portfolio: full `/trade analyze` for tickers that need fresh
context, fast `/trade quick` for ones that don't, escalation to analyze when
a quick reveals a signal change, then a single TRADE-ROUTINE digest at the
end. This skill is what turns the AI Trading Analyst from a one-off
research tool into a daily-cadence portfolio monitor.

**DISCLAIMER: This is for educational and research purposes only. Not
financial advice. Always do your own due diligence.**

> ⚠️ **NOT SAFE TO INVOKE CONCURRENTLY.** Pinecone upserts are idempotent,
> but CWD file writes (`TRADE-ROUTINE-<ts>.md`, `TRADE-QUICK-*.md`) and
> Slack deliveries are NOT. Run one routine at a time per CWD. If you need
> parallel runs across portfolios, use distinct CWDs and distinct
> `PINECONE_NAMESPACE` values.

---

## Activation

Activates on:
- `/trade routine` — default daily sweep
- `/trade routine --max-escalations N` — override the analyze-cap
  (default 10; raise for portfolios > 30 tickers)
- `/trade routine --cloud` — after the local sweep completes, posts the
  TRADE-ROUTINE digest to `#portfolio-updates` (channel ID `C0B712ARA7M`)
  via `mcp__claude_ai_Slack__slack_send_message` and uploads the full
  `TRADE-ROUTINE-<ts>.md` to the InvestmentSummary Drive folder
  (`1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm`) via
  `mcp__claude_ai_Google_Drive__create_file`. Slack OR Drive failures
  are non-fatal warnings (digest still in CWD; per-ticker reports
  already archived via `ingest --archive`). See "Output routing —
  cloud branch" below for the full delivery contract.
- `/trade routine --cloud --slack-channel <id>` — overrides the default
  Slack destination (test channel, personal DM channel ID, different
  workspace fork). Drive upload still targets InvestmentSummary.
- `/trade routine --cloud --autotrader` — after Slack + Drive delivery,
  fires the AutoTrader webhook (`POST /webhook/sweep`) at the URL in
  `AUTOTRADER_WEBHOOK_URL` (env var) with the sweep signal payload signed
  via HMAC-SHA256. Requires `AUTOTRADER_WEBHOOK_URL` and
  `AUTOTRADER_WEBHOOK_SECRET` to be set; missing either skips the step
  with a `[warn]`. See "Step W — AutoTrader webhook" below.

---

## Pre-flight (run BEFORE the loop)

### P0 — Parse flags

Parse the command line for:
- `--max-escalations N` → set `MAX_ESCALATIONS` (default 10)
- `--slack-channel <id>` → set `SLACK_CHANNEL_ID`; **default
  `C0B712ARA7M` (`#portfolio-updates`)**. Only consulted when `--cloud`
  is set; otherwise captured and ignored.
- `--cloud` → set `CLOUD_MODE=1`. Triggers the cloud delivery branch
  after the local sweep completes (see "Output routing — cloud
  branch"). If unset, `SLACK_CHANNEL_ID` is ignored and the routine
  finishes after the local terminal summary.
- `--no-options` → set `NO_OPTIONS=1`. Skips the Step 3d options overlay
  entirely. Default (flag unset): the overlay runs for every analyze-tier
  ticker, naturally bounded by the escalation cap (it only fires where
  analyze fired).
- `--autotrader` → set `AUTOTRADER_MODE=1`. Only active when `--cloud`
  is also set. Fires the AutoTrader webhook after Slack + Drive delivery
  (see "Step W" in the cloud branch). Silently ignored if `--cloud` is
  not set.

### P1 — Generate `run_id`

```bash
RUN_ID="routine-$(date -u +%Y%m%d-%H%M)-$( (openssl rand -hex 3 2>/dev/null) || (head -c 24 /dev/urandom | xxd -p | head -c 6) )"
echo "$RUN_ID"
```

The `(openssl rand -hex 3 2>/dev/null) || (...)` form falls back to
`/dev/urandom` when openssl isn't installed (some minimal container
environments). Format: `routine-<YYYYMMDD-HHMM>-<6hex>` (matches the
RUN_ID grammar `trade-analyze`'s ingest call uses).

### P2 — Load holdings

Read the canonical ticker list directly from Google Drive by invoking the
`/trade holdings` skill. It locates the holdings file in the
`InvestmentSummary` Drive folder, parses it, and produces the normalized,
deduped, uppercase ticker list (plus a `## Positions` table when share counts
are present). The routine consumes that result directly — it does NOT read or
write any local holdings cache, and it never writes to the current working
directory.

Decision tree:
- **`/trade holdings` returns a ticker list** → use it as the canonical
  holdings for this sweep.
- **Drive MCP unavailable, the holdings file isn't found, or zero tickers
  are extracted** → abort with:
  `[error] No holdings available — Drive could not be read. Connect the
  Google Drive MCP and confirm the InvestmentSummary folder holds a readable
  holdings file, then re-run. Aborting routine.`
  Exit cleanly; do NOT continue with an empty ticker list, and do NOT fall
  back to any stale local copy.

Take the `## Tickers` list from the `/trade holdings` result as the array of
tickers for the sweep loop.

### P3 — Initialize counters

```
ESCALATIONS_USED=0
TIER_COUNTS = { analyze: 0, quick: 0, escalated: 0, deferred: 0, options: 0 }
TICKER_RESULTS = []   # one row per ticker for the digest
```

---

## Per-ticker loop

For each ticker `T` in the holdings list:

### Step 1 — Tier decision

```bash
TIER=$(python3 ~/.claude/skills/trade/scripts/trade_memory.py recommend-tier "$T" 2>/dev/null)
```

`recommend-tier` is contractually safe — if Pinecone is unavailable it
prints `analyze` and exits 0. Treat unexpected non-`analyze`/`quick` output
as a hard failure for THIS ticker (skip it, record an error row in the
digest, continue).

### Step 2 — Capture prior state (for digest deltas)

Before dispatching anything, fetch the ticker's **prior** record so the
digest can show before/after deltas:

```bash
PRIOR=$(python3 ~/.claude/skills/trade/scripts/trade_memory.py latest "$T" 2>/dev/null)
```

Parse `PRIOR` as JSON. Capture:
- `prior_signal` (may be null on first-ever sweep)
- `prior_score` (composite for ANALYSIS records, or per-dim for everything
  else; may be null)
- `prior_type` (ANALYSIS / QUICK / etc.)
- `prior_date` (`generated_date`)

If `PRIOR` is `{}` (no prior records), all four are null — this is a
**cold ticker**.

### Step 3a — If `TIER == analyze` (full sweep)

**Check the escalation cap first.** If `ESCALATIONS_USED >= MAX_ESCALATIONS`,
downgrade to quick:
```
echo "[warn] escalation cap $MAX_ESCALATIONS reached; ticker $T deferred to next run" >&2
TIER_COUNTS.deferred++
# add a "deferred" row to TICKER_RESULTS; CONTINUE the loop without dispatching
continue
```

Otherwise dispatch the analyze:
```
# In the LLM context, invoke /trade analyze <T>. The trade-analyze skill
# writes TRADE-ANALYSIS-<T>.md and runs the non-fatal ingest itself
# (per slice 4 Step 4: `trade_memory.py ingest --archive --run-id ...
# || true`).
# Pass the routine's RUN_ID through so all chunks from this sweep group
# together: set the env var TRADE_RUN_ID=$RUN_ID before invoking, and
# the trade-analyze skill prose prefers $TRADE_RUN_ID over its
# generated RUN_ID when present (additive — older trade-analyze
# versions still work, they just use their own RUN_ID).
ESCALATIONS_USED++
TIER_COUNTS.analyze++
```

After the analyze completes, re-fetch `latest $T --type ANALYSIS` to get
the **new** signal/score for the digest row.

### Step 3b — If `TIER == quick` (snapshot + escalation check)

Dispatch `/trade quick $T` and **capture its terminal output** into a
shell variable:
```
QUICK_OUTPUT=<output from /trade quick $T invocation>
```

`/trade quick` is terminal-only by design (does NOT write a file). The
routine's responsibility is to harvest that output and build a
`TRADE-QUICK-<T>-<YYYYMMDD-HHMM>.md` file with the §2 QUICK-subset
frontmatter so the memory layer can index it.

**Extract from `QUICK_OUTPUT`:**
- `SIGNAL` — the value on the `SIGNAL:` line. `/trade quick` emits **4
  labels** (BUY / HOLD / SELL / AVOID), which must be projected onto the
  **6-value** Signal enum for the QUICK record's frontmatter:

  | trade-quick emits | QUICK frontmatter signal | Covers Signal-enum values |
  |---|---|---|
  | BUY | `BUY` | STRONG BUY, BUY |
  | HOLD | `HOLD` | HOLD, **NEUTRAL** |
  | SELL | `CAUTION` | CAUTION |
  | AVOID | `AVOID` | AVOID |

  `HOLD` covering both `HOLD` (score 55–69) and `NEUTRAL` (40–54) is the
  intentional consequence of trade-quick's coarser signal grammar — the
  escalation matrix below must respect this projection to avoid spurious
  escalations every sweep on NEUTRAL-prior tickers.
- `PRICE` — the dollar value on the `Price:` line.
- `COMPANY` — the name on the header line (after the ticker, before the
  date).

Build `TRADE-QUICK-<T>-$(date +%Y%m%d-%H%M).md` in CWD:

```markdown
---
trade_report: true
schema_version: 1
ticker: <T>
company: <COMPANY>
report_type: QUICK
generated_at: <ISO-8601 timestamp with tz>
signal: <STRONG BUY|BUY|HOLD|NEUTRAL|CAUTION|AVOID>
grade: <A+|A|B|C|D|F>   # derived from signal via the 6-band table;
                        # /trade quick doesn't emit a score so we map
                        # signal→grade directly (BUY→A, HOLD→B,
                        # NEUTRAL→C, CAUTION→D, AVOID→F, STRONG BUY→A+)
price_at_analysis: <PRICE>
run_id: <RUN_ID>
---

# Quick Snapshot: <T> — <COMPANY>

> Routine sweep <RUN_ID> | Tier: quick

(verbatim QUICK_OUTPUT captured from /trade quick <T>)
```

Then ingest it (non-fatal):
```bash
python3 ~/.claude/skills/trade/scripts/trade_memory.py \
    ingest "TRADE-QUICK-${T}-$(date +%Y%m%d-%H%M).md" \
    --archive --run-id "$RUN_ID" || true
```

`TIER_COUNTS.quick++`

**Apply the escalation decision matrix:**

| Prior stored signal | New quick signal | Decision |
|---------------------|------------------|----------|
| null (first quick) | any | keep quick, no escalation (recommend-tier already decided quick) |
| same as prior | same | keep quick |
| **HOLD** | **HOLD** (or any quick-emitted HOLD covering a prior NEUTRAL) | keep quick — HOLD covers both HOLD and NEUTRAL bands per the projection table above |
| **NEUTRAL** | **HOLD** | keep quick — HOLD is the quick-equivalent of NEUTRAL (40–54 band) |
| **STRONG BUY** | **BUY** | keep quick — BUY covers both STRONG BUY and BUY bands |
| any | otherwise different | **ESCALATE** — proceed to Step 3c |

The "covers" rules above prevent a guaranteed escalation loop for tickers
whose last full analysis landed in the NEUTRAL (40–54) or STRONG BUY (85+)
bands — `/trade quick` cannot produce those exact labels (it only emits 4),
so a naïve string equality would flip every sweep. Treating HOLD as
covering {HOLD, NEUTRAL} and BUY as covering {STRONG BUY, BUY} aligns the
4-label quick output with the 6-label Signal enum for change-detection
purposes. A genuine band shift (e.g., HOLD prior → BUY new) still escalates
correctly.

### Step 3c — Escalation (signal change detected in a quick)

Check the cap (same as Step 3a). If exhausted: mark `deferred` and skip;
the quick record stays as the sweep's tier outcome.

If room remains:
1. Print on stderr: `[escalate] $T: signal change ${prior_signal} →
   ${new_quick_signal}; running /trade analyze`
2. Dispatch `/trade analyze $T` (same as Step 3a; trade-analyze does its
   own ingest with the routine's `TRADE_RUN_ID`)
3. `ESCALATIONS_USED++`; `TIER_COUNTS.escalated++`
4. The quick file is KEPT as a supplementary record — both records appear
   in `timeline $T` (quick first because it has the earlier minute-level
   timestamp; analyze supersedes for tier decisions on the next sweep
   because its ANALYSIS type + newer timestamp wins in `latest`)

### Step 3d — Options overlay (analyze-tier tickers only)

Run ONLY when this ticker was processed at the **analyze** or **escalated**
tier this sweep (NOT quick-kept, NOT deferred) and `--no-options` was not
passed (`NO_OPTIONS` unset). This focuses options on positions that got a
fresh full read and keeps cost bounded by the escalation cap.

1. Resolve position context from the `/trade holdings` result loaded in P2:
   - `POSITION_BIAS=LONG` (every routine ticker is a holding).
   - If that result includes a `## Positions` row for `$T` with a numeric
     Shares value → `POSITION_SHARES=<that number>`; else
     `POSITION_SHARES=unknown`.
2. Reuse the fresh analyze result from Step 3a/3c:
   `ANALYZE_SIGNAL=<new_signal>`, `COMPOSITE_SCORE=<new_score>`.
3. Capture one timestamp for this overlay so the filename and the ingest call
   can't drift across a minute boundary:
   ```bash
   OPTS_TS=$(date +%Y%m%d-%H%M)
   ```
4. In the LLM context, invoke `/trade options $T` passing POSITION_BIAS,
   POSITION_SHARES, ANALYZE_SIGNAL, COMPOSITE_SCORE, and `RUN_ID=$RUN_ID`. The
   trade-options skill writes `TRADE-OPTIONS-$T-$OPTS_TS.md` with OPTIONS
   frontmatter.
5. Ingest it non-fatally (mirrors the QUICK ingest in Step 3b):
   ```bash
   python3 ~/.claude/skills/trade/scripts/trade_memory.py \
       ingest "TRADE-OPTIONS-${T}-${OPTS_TS}.md" \
       --archive --run-id "$RUN_ID" || true
   ```
6. `TIER_COUNTS.options++`. Capture `recommended_strategy` and
   `strategy_outlook` from the report's frontmatter for the digest row.

If `/trade options` fails or returns no usable strategy, log
`[warn] $T: options overlay skipped (<reason>)` on stderr and continue — the
overlay is supplementary and MUST NOT fail the sweep.

### Step 4 — Record digest row

Push a row into `TICKER_RESULTS`:
```
{
  ticker: T,
  tier: <analyze|quick|escalated|deferred>,
  prior_signal, new_signal,
  prior_score, new_score,
  delta_score: new_score - prior_score (null if either side null),
  prior_date,
  nearest_catalyst_date: (from new record),
  options_strategy: <recommended_strategy or null>,
  options_outlook: <strategy_outlook or null>,
  notes: <any [warn] / [escalate] lines for this ticker>,
}
```

---

## Post-loop — Digest assembly

After every ticker is processed, write `TRADE-ROUTINE-<YYYYMMDD-HHMM>.md`
in CWD. The timestamp matches the one in `RUN_ID` for traceability.

```markdown
---
trade_routine: true
schema_version: 1
run_id: <RUN_ID>
generated_at: <ISO-8601 with tz>
ticker_count: <N>
analyze_count: <TIER_COUNTS.analyze>
quick_count: <TIER_COUNTS.quick>
escalated_count: <TIER_COUNTS.escalated>
deferred_count: <TIER_COUNTS.deferred>
options_count: <TIER_COUNTS.options>
max_escalations: <MAX_ESCALATIONS>
---

# Portfolio Routine — <RUN_ID>

> Generated <YYYY-MM-DD HH:MM UTC> | <N> tickers | analyze=<X>, quick=<Y>, escalated=<Z>, deferred=<W>
> **NOT FINANCIAL ADVICE — research output only.**

## Summary

<one paragraph: how many fresh analyses; how many quicks; any notable
escalations; any deferrals due to cap; any data gaps>

## Per-Ticker Results

| Ticker | Tier | Prior Signal | New Signal | Δ Score | Prior → New | Nearest Catalyst | Options | Notes |
|--------|------|--------------|------------|---------|-------------|------------------|---------|-------|
| AAPL | analyze | BUY | BUY | +2 | 72 → 74 | 2026-07-31 (earnings) | INCOME: Covered Call | — |
| CLOV | quick | AVOID | AVOID | — | — | — | — | held |
| MARA | escalated | HOLD | BUY | +18 | 55 → 73 | — | INCOME: Cash-Secured Put | signal flipped HOLD→BUY → re-analyzed |
| NIO | deferred | HOLD | — | — | — | — | escalation cap reached |
| ... | ... | ... | ... | ... | ... | ... | ... |

> **Risk score Δ is INVERTED** — a positive Δ means risk decreased (the
> position got SAFER); a negative Δ means risk increased.

## New Alerts

<list any: signal changes, catalysts within 14 days, score moves > 10
points, any deferred tickers>

## Tier Distribution

| Tier | Count |
|------|-------|
| analyze | <X> |
| quick | <Y> |
| escalated | <Z> |
| deferred | <W> |

## Data Gaps

<list any tickers that errored, had stale data, or returned unexpected
recommend-tier output>

---

> **DISCLAIMER:** This routine output is generated by an AI system for
> educational and research purposes only. It is NOT financial advice. The
> tier decisions and signal classifications are derived from public data
> via web searches and may be incomplete, delayed, or inaccurate. Always
> conduct your own due diligence and consult a licensed financial advisor
> before making investment decisions.
```

Ingest the digest too so future sessions can recall "the last routine
sweep" — but the digest is NOT a per-ticker record so we do NOT use
`trade_memory.py ingest` here (the schema is for per-ticker reports). The
routine digest lives only as a CWD file (plus a Drive archive copy when
`--cloud` is set; see "Output routing — cloud branch").

---

## Output routing

### Local (always)

- `TRADE-ROUTINE-<ts>.md` in CWD
- Per-ticker analysis/quick reports in CWD (already written by the
  respective skills)
- All Pinecone records have `run_id = <RUN_ID>`
- Print a concise terminal summary at the end:
  ```
  ✓ Routine <RUN_ID> complete
    Tickers: <N>  |  analyze=<X>  quick=<Y>  escalated=<Z>  deferred=<W>
    Digest: TRADE-ROUTINE-<ts>.md
    Notable: <one-line summary of any signal changes / escalations>
  ```

### Cloud branch (when `--cloud` is set)

After the local terminal summary prints, perform Slack delivery, then
Drive upload, then a one-line cloud-summary. Both deliveries are
**non-fatal warnings** on failure — the digest already exists in CWD
and per-ticker records already landed in Pinecone (via `ingest`) and
Drive (via `ingest --archive`), so the routine is complete even if
delivery fails. Do NOT exit non-zero on Slack/Drive failure; print a
single `[warn] …` line on stderr and continue to the next step.

**Pre-flight env check.** Verify `PINECONE_PROXY_URL` and
`PINECONE_PROXY_TOKEN` are present in the environment. If both are
set, `trade_memory.py` auto-routes all Pinecone ops through the
Vercel HTTPS proxy (slice 7.5). If either is missing, print:
`[warn] --cloud set but PINECONE_PROXY_URL / PINECONE_PROXY_TOKEN
missing; per-ticker records used the local Pinecone SDK path.
Continuing with Slack + Drive delivery.` Continue — the cloud branch
is about delivery destinations, not transport.

**Step 1 — Slack delivery.** Resolve the channel:

```
TARGET_CHANNEL_ID = SLACK_CHANNEL_ID  # from --slack-channel <id>, default C0B712ARA7M
```

Assemble a Slack-friendly digest body — short version of the
TRADE-ROUTINE markdown: title line + `Tickers / analyze / quick /
escalated / deferred / options` counters + the per-ticker delta table +
an **Options posture** block (one line per ticker where the overlay ran,
omitted entirely if `options_count == 0`) + the Notable / Data Gaps
sections + a footer pointing to the Drive copy. Strip the in-CWD-only
sections (full report URLs, raw fixture listings). Include the disclaimer.

The Options posture block (only for tickers whose Step 3d overlay ran):

```
Options posture (analyze-tier):
  • AAPL — INCOME / Covered Call
  • MARA — HEDGE / Protective Put
```

It is part of the digest body, so it falls under the same ≤3000 →
message / >3000 → canvas size branch below.

Then branch on payload size:

| Body length | Delivery mechanism |
|---|---|
| ≤ 3000 chars | `mcp__claude_ai_Slack__slack_send_message` with `channel=TARGET_CHANNEL_ID` and `text=<body>` |
| > 3000 chars | `mcp__claude_ai_Slack__slack_create_canvas` with `channel_id=TARGET_CHANNEL_ID`, a title like `TRADE-ROUTINE <RUN_ID>`, and the full digest markdown as content. Then post a one-line `slack_send_message` to the same channel linking the canvas. |

On any Slack error (channel not found, rate-limited, token expired,
canvas-creation failure), print:
`[warn] Slack delivery failed (<reason>); digest still in CWD as
TRADE-ROUTINE-<ts>.md` and continue to Step 2.

**Step 2 — Drive archive upload.** Upload the full
`TRADE-ROUTINE-<ts>.md` to the InvestmentSummary folder:

```
DRIVE_ARCHIVE_FOLDER_ID = "1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm"
```

Call `mcp__claude_ai_Google_Drive__create_file` with the digest
contents, `parents=[DRIVE_ARCHIVE_FOLDER_ID]`, `name=TRADE-ROUTINE-<ts>.md`,
and `mime_type="text/markdown"`. The per-ticker reports are NOT
re-uploaded here — `trade_memory.py ingest --archive` already
deposited them in the same folder under `<TICKER>/` subfolders
during the sweep.

On any Drive error (auth expired, folder not found, quota exceeded),
print: `[warn] Drive upload failed (<reason>); digest still in CWD`
and continue to Step 3.

**Step 3 — Cloud summary line.** Append one line to the terminal
summary already printed by the local block:

```
  Cloud: slack=<ok|warn>  drive=<ok|warn>  channel=<TARGET_CHANNEL_ID>
```

Use `ok` if the call returned success, `warn` if it failed (the
preceding stderr warning already explained why).

**Step W — AutoTrader webhook** (only when `--autotrader` flag is set)

After Step 3, if `AUTOTRADER_MODE=1`, fire the signal payload to the
AutoTrader webhook server (`autotrader/signals/webhook.py`).

**Pre-flight:** Check that both `AUTOTRADER_WEBHOOK_URL` and
`AUTOTRADER_WEBHOOK_SECRET` are set in the environment. If either is
missing, print:
`[warn] --autotrader set but AUTOTRADER_WEBHOOK_URL / AUTOTRADER_WEBHOOK_SECRET
missing; skipping AutoTrader webhook delivery.` and skip this step.

**Build the payload** (`/tmp/sweep_payload.json`):
```json
{
  "run_id": "<RUN_ID>",
  "sweep_date": "<YYYY-MM-DD>",
  "generated_at": "<ISO-8601 timestamp with tz>",
  "ticker_count": <N>,
  "signal_changes": [ /* only tickers where prior_signal != new_signal */ ],
  "all_positions": [ /* every ticker with prior/new signal + score + delta */ ],
  "alerts": {
    "high_confidence_changes": [ /* entries where abs(delta)/10 >= 0.6 */ ],
    "risk_flags": [ /* tickers with risk_score < 30 */ ]
  }
}
```

Each position entry shape:
```json
{
  "ticker": "AAPL",
  "prior_signal": "HOLD",  "new_signal": "BUY",
  "prior_score": 65,       "new_score": 72,
  "delta": 7,
  "confidence": 0.7,        /* abs(delta) / 10 */
  "signal_changed": true,
  "above_threshold": true   /* confidence >= 0.6 */
}
```

**Sign and POST.** The server (`autotrader/signals/webhook.py`) validates
two headers using constant-time comparison over the exact bytes received.
Both headers are **required** — sending only one always returns 401:

```bash
SECRET="$AUTOTRADER_WEBHOOK_SECRET"
# Compact JSON — no trailing newline (bash $() strips it automatically)
BODY=$(python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin), separators=(',',':')))" < /tmp/sweep_payload.json)
SIG="sha256=$(echo -n "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')"

curl -s -w "\nHTTP %{http_code}" -X POST "$AUTOTRADER_WEBHOOK_URL/webhook/sweep" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: $SECRET" \
  -H "X-Webhook-Signature: $SIG" \
  -d "$BODY"
```

**Why two headers?**
- `X-Webhook-Token` — the raw secret; server uses it to look up the
  expected signing key per-client.
- `X-Webhook-Signature` — `sha256=<hex>` HMAC-SHA256 of the **compact**
  JSON body (no pretty-print, no trailing newline). Server hashes the
  raw received bytes and compares constant-time; whitespace differences
  will break the signature.

**Interpret the response:**
- `HTTP 202` + `{"status":"accepted","signals":<N>}` — success; N is the
  number of signal entries the server coerced (above-threshold entries
  that generated AutoTrader actions). Log the response body.
- `HTTP 401` — both headers missing or HMAC mismatch; print the error and
  mark as warn.
- Other 4xx/5xx — non-fatal warn; payload still in `/tmp/sweep_payload.json`.

On any error, print `[warn] AutoTrader webhook failed (<status> <reason>);
payload at /tmp/sweep_payload.json` and continue. The webhook is
supplementary and MUST NOT abort the sweep or the cloud delivery.

**Append to the cloud summary line:**
```
  Cloud: slack=<ok|warn>  drive=<ok|warn>  autotrader=<ok|warn|skip>  channel=<TARGET_CHANNEL_ID>
```

`skip` when `--autotrader` was not passed; `ok`/`warn` from the HTTP
response above.

---

**Different-user note.** If your Slack workspace doesn't contain
`C0B712ARA7M`, either create a `#portfolio-updates` channel in your
workspace and update the hardcoded ID at the top of this skill (and
`skills/trade-holdings/SKILL.md`), or pass `--slack-channel <id>`
on every cloud routine. Same applies to the Drive folder if your
holdings live somewhere other than InvestmentSummary.

---

## Error handling

| Scenario | Routine behavior |
|---|---|
| Drive MCP unavailable / holdings file not found / 0 tickers extracted | Abort with a clear single-line message + recovery hint (Drive-only; no local-cache fallback) |
| `PINECONE_API_KEY` missing/invalid | `recommend-tier` safely returns `analyze`; routine continues at full-tier; `ingest` calls fail silently via `\|\| true`; digest notes "memory unavailable — all tickers ran at analyze tier" |
| `/trade analyze <T>` fails on a single ticker | Skip that ticker; record an error row in the digest; continue with the next |
| `/trade quick <T>` fails on a single ticker | Same as analyze failure — record + continue |
| Escalation cap reached | Downgrade subsequent analyzes to quicks; flag deferred tickers in the digest |
| Holdings file has < 1 ticker | Abort with "no tickers to sweep" |
| Holdings file has > 100 tickers | Warn but continue; the escalation cap protects subagent budget |
| `--cloud` set, `PINECONE_PROXY_URL`/`PINECONE_PROXY_TOKEN` missing | Warn (see "Pre-flight env check"); continue Slack + Drive delivery |
| `--cloud` set, Slack send fails (channel not found / rate-limit / token expired / canvas error) | `[warn]` on stderr; continue to Drive step; digest still in CWD |
| `--cloud` set, Drive upload fails (auth expired / folder missing / quota) | `[warn]` on stderr; continue to cloud-summary line; digest still in CWD |
| `--cloud --autotrader` set, `AUTOTRADER_WEBHOOK_URL`/`AUTOTRADER_WEBHOOK_SECRET` missing | `[warn]` on stderr; mark `autotrader=skip` in cloud summary; continue |
| `--cloud --autotrader` set, webhook returns 401 | Both headers required (`X-Webhook-Token` + `X-Webhook-Signature`); verify secret and that both are sent; `[warn]` + payload at `/tmp/sweep_payload.json` |
| `--cloud --autotrader` set, webhook returns other 4xx/5xx | `[warn]` on stderr; payload at `/tmp/sweep_payload.json` for manual retry |

---

## Rules

1. ALWAYS generate `RUN_ID` first — every record from this sweep must
   share it so `query "...run_id:<RUN_ID>"` returns the full sweep.
2. ALWAYS respect the escalation cap — protecting subagent budget on
   volatile-market days is the cap's whole purpose.
3. NEVER invoke concurrent routines in the same CWD — file writes will
   collide.
4. ALWAYS ingest non-fatally (`|| true` on every `trade_memory.py
   ingest`); memory failures must NEVER abort the sweep.
5. ALWAYS produce a digest, even if some tickers errored — the digest's
   "Data Gaps" section is how the user knows what failed.
6. ALWAYS print the disclaimer in the digest.
7. The `/trade quick` skill is terminal-only; THIS skill (the routine) is
   responsible for capturing its output and assembling the
   TRADE-QUICK-*.md file with the §2 QUICK-subset frontmatter (slice 6
   gate D.15).

**DISCLAIMER: This is for educational and research purposes only. Not
financial advice. Always do your own due diligence.**
