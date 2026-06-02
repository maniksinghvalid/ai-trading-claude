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
> parallel runs across portfolios, use distinct CWDs and (eventually,
> slice 7.5+) distinct Pinecone namespaces.

---

## Activation

Activates on:
- `/trade routine` — default daily sweep
- `/trade routine --max-escalations N` — override the analyze-cap
  (default 10; raise for portfolios > 30 tickers)
- `/trade routine --cloud` — **slice 8 only;** posts the digest to
  `#portfolio-updates` (channel ID `C0B712ARA7M`) by default via
  `slack_send_message`. While slice 8 isn't wired yet, print
  "cloud mode not yet implemented (slice 8 deliverable); falling
  back to local mode" and continue. Do NOT silently drop the flag.
- `/trade routine --cloud --slack-channel <id>` — optional override of
  the default destination (e.g., a test channel or a personal DM
  channel ID). Same slice-8 "not yet implemented" notice applies.

---

## Pre-flight (run BEFORE the loop)

### P0 — Parse flags

Parse the command line for:
- `--max-escalations N` → set `MAX_ESCALATIONS` (default 10)
- `--slack-channel <id>` → set `SLACK_CHANNEL_ID`; **default
  `C0B712ARA7M` (`#portfolio-updates`)**. Capture but ignore for slice 6
  (slice 8 wires the actual `slack_send_message` call).
- `--cloud` → capture; print the slice-8 notice; continue local

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

Try Drive first via the `/trade holdings` skill (Drive read + cache write).
Then read the cache to get the canonical ticker list:

```bash
cat ~/.claude/trade/TRADE-HOLDINGS.md 2>/dev/null
```

Decision tree:
- **Drive read succeeds via `/trade holdings`** → use that list; the cache
  is now fresh.
- **Drive MCP unavailable or holdings file not found** → read the existing
  `~/.claude/trade/TRADE-HOLDINGS.md` cache; print on stderr:
  `[warn] Drive unavailable; using cached holdings from <YYYY-MM-DD>`.
  The date comes from the cache's `source_modified` frontmatter or its
  mtime.
- **Both unavailable** (no Drive AND no cache file) → abort with:
  `[error] No holdings available. Run /trade holdings once with Drive
  connected to populate the cache, or paste a list into
  ~/.claude/trade/TRADE-HOLDINGS.md manually. Aborting routine.`
  Exit cleanly; do NOT continue with an empty ticker list.

Parse the cache's `## Tickers` bullet list to get the array of tickers.

### P3 — Initialize counters

```
ESCALATIONS_USED=0
TIER_COUNTS = { analyze: 0, quick: 0, escalated: 0, deferred: 0 }
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
max_escalations: <MAX_ESCALATIONS>
---

# Portfolio Routine — <RUN_ID>

> Generated <YYYY-MM-DD HH:MM UTC> | <N> tickers | analyze=<X>, quick=<Y>, escalated=<Z>, deferred=<W>
> **NOT FINANCIAL ADVICE — research output only.**

## Summary

<one paragraph: how many fresh analyses; how many quicks; any notable
escalations; any deferrals due to cap; any data gaps>

## Per-Ticker Results

| Ticker | Tier | Prior Signal | New Signal | Δ Score | Prior → New | Nearest Catalyst | Notes |
|--------|------|--------------|------------|---------|-------------|------------------|-------|
| AAPL | analyze | BUY | BUY | +2 | 72 → 74 | 2026-07-31 (earnings) | — |
| CLOV | quick | AVOID | AVOID | — | — | — | held |
| MARA | escalated | HOLD | BUY | +18 | 55 → 73 | — | signal flipped HOLD→BUY → re-analyzed |
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
routine digest lives only as a CWD file + Drive archive (slice 8).

---

## Output routing (current = local)

For slice 6:
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

For slice 8 (not yet wired):
- `--cloud` will add Slack channel post (`#portfolio-updates`, channel ID
  `C0B712ARA7M` — hardcoded default per the plan-doc §4) + Drive digest
  upload. Delivery via `slack_send_message`; long digests escalate to
  `slack_create_canvas`.
- `--slack-channel <id>` overrides the default channel for one routine
  (test channel, personal DM, etc.).
- Different-user note: if your Slack workspace doesn't contain
  `C0B712ARA7M`, either create a `#portfolio-updates` channel in your
  workspace and update the hardcoded ID here, or pass `--slack-channel
  <id>` per-routine.
- This skill prints "cloud mode not yet implemented (slice 8); falling
  back to local mode" when those flags are passed.

---

## Error handling

| Scenario | Routine behavior |
|---|---|
| Drive MCP unavailable, cache present | Continue with cached holdings + stderr warning |
| Drive MCP unavailable, no cache | Abort with clear single-line message + recovery hint |
| `PINECONE_API_KEY` missing/invalid | `recommend-tier` safely returns `analyze`; routine continues at full-tier; `ingest` calls fail silently via `\|\| true`; digest notes "memory unavailable — all tickers ran at analyze tier" |
| `/trade analyze <T>` fails on a single ticker | Skip that ticker; record an error row in the digest; continue with the next |
| `/trade quick <T>` fails on a single ticker | Same as analyze failure — record + continue |
| Escalation cap reached | Downgrade subsequent analyzes to quicks; flag deferred tickers in the digest |
| Holdings file has < 1 ticker | Abort with "no tickers to sweep" |
| Holdings file has > 100 tickers | Warn but continue; the escalation cap protects subagent budget |

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
