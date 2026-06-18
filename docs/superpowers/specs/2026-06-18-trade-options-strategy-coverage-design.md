# Design: Extend `trade-options` with six high-value strategies

**Date:** 2026-06-18
**File touched:** `skills/trade-options/SKILL.md` (only)
**Status:** Approved — ready for implementation plan

## Goal

The Options Strategy Advisor covers ~15 core strategies but is missing several
that are decision-relevant for a long-holdings portfolio. Close the high-value
gaps **without** turning the advisor into a strategy encyclopedia. Explicitly
out of scope: naked call, butterfly (incl. broken-wing), 4-leg condor, ratio
spreads, backspreads, synthetics, risk reversal, box spread, jade lizard.

## What gets added (6 strategies)

Long straddle, long strangle, short straddle, covered strangle, Poor Man's
Covered Call (PMCC), and the Wheel. (Short strangle, iron condor, iron
butterfly already exist.)

## Schema impact: NONE

Verified against `scripts/trade_schemas.py`:
- `strategy_outlook` is validated against `{BULLISH, BEARISH, NEUTRAL, INCOME, HEDGE}`.
  All six additions map to existing values: long/short straddle + strangle →
  `NEUTRAL`; PMCC → `BULLISH`; Wheel + covered strangle → `INCOME`.
- `recommended_strategy` is free text — new strategy names need no enum change.

No `schema_version` bump, no `trade_schemas.py` edit, no `sync_proxy_schemas.sh`
run, no proxy redeploy. This is a pure prompt edit.

## Changes (4 edits, all within `skills/trade-options/SKILL.md`)

### 1. Neutral/Volatility strategy table (current lines 167–174)

Add four rows so volatility structures become first-class selectable strategies
(today long/short straddles and strangles only appear in passing in the IV
framework and earnings sections):

| Strategy | When to Use | Max Profit | Max Loss | Breakeven |
|----------|-------------|------------|----------|-----------|
| Long Straddle | Very low IV + expect big move, direction unknown | Unlimited | Both premiums paid | Strike +/- total premium |
| Long Strangle | Low IV + expect big move, cheaper than straddle | Unlimited | Both premiums paid | Strikes +/- total premium |
| Short Straddle | Very high IV + pin expected (undefined risk) | Total credit | Unlimited | Strike +/- credit |
| Covered Strangle | LONG + high IV + range-bound + willing to add shares | Credit + upside to call strike | Stock downside + put assignment | Complex (two breakevens) |

### 2. Primary strategy matrix (current lines 130–140)

Add two rows and tweak one position-sizing guard:

- New row: `LONG | STRONG BUY / BUY | Low IV (rank <50) | PMCC (if shares <100) / Hold or Call Diagonal (if >=100) | BULLISH | grow, capital-efficient when share count is small`
- New row: `FLAT | STRONG BUY / BUY | High IV | The Wheel (CSP leg) | INCOME | grow, systematic income rotation`
  - The existing bare Cash-Secured Put row stays; the Wheel row reframes the
    same CSP entry as the first leg of a rotation when the trader wants the
    systematic plan.
- Update the position-sizing guard (current line ~149): when LONG but
  `POSITION_SHARES < 100`, the fallback becomes **PMCC** (capital-efficient
  covered-call substitute) rather than only "the FLAT row's directional play."

### 3. New subsection: "Systematic & Capital-Efficient Plays"

Insert after the position-sizing block (current ~line 150). Short prose for the
multi-step mechanics the one-row tables cannot capture:

- **Poor Man's Covered Call (PMCC):** long-dated deep-ITM call (~80 delta,
  6–12 months out) as a stock substitute, short near-term OTM call against it.
  Note: the long call must cover the short strike width; carries early-assignment
  / ex-dividend risk on the short leg; far cheaper than 100 shares but no
  dividend and exposed to long-call theta.
- **The Wheel:** sell cash-secured put → if assigned, own 100 shares → sell
  covered calls → if called away, return to selling CSPs. Frame as an `INCOME`
  rotation; cross-reference the Cash-Secured Put and Covered Call rows. Best in
  elevated-IV, range-bound, fundamentally-acceptable names you'd be content to own.

### 4. Quality Standards (current lines 470–477)

Add one additive rule: long straddles/strangles require a low / very-low
IV-rank justification (buying premium — do not buy expensive volatility); short
straddle and covered strangle must carry the undefined-risk warning already
mandated by existing rule 3.

## Out of scope / unchanged

Frontmatter, Data Collection Phase, Output Format, Calculation Guidance, Edge
Cases — untouched. No new WebSearch steps required; existing IV / chain / flow
data already supports these strategies.

## Verification

- `strategy_outlook` enum unchanged → existing schema validation still passes.
- Re-read the edited SKILL.md to confirm: every new table row has all five
  columns; the two new matrix rows have all six columns; the IV-driven
  premium-buy/sell logic (Quality Standard rule 2) is consistent with the new
  long-vol rows (long straddle/strangle gated to low IV).
- No install/test harness exists for prompts; correctness is by inspection
  against the cross-file contracts in `CLAUDE.md`.
