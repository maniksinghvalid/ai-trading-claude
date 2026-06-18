# trade-options Strategy Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add six high-value options strategies (long/short straddle, long strangle, covered strangle, PMCC, the Wheel) to the Options Strategy Advisor without turning it into a strategy encyclopedia.

**Architecture:** Pure prompt edit to a single Markdown file, `skills/trade-options/SKILL.md`. Four content edits: (1) add four rows to the Neutral/Volatility strategy table; (2) modify two existing primary-matrix rows in place so PMCC and the Wheel become selectable primaries (modify, not add — the matrix contract is one primary per position×signal×IV cell); (3) point the sub-100-share position-sizing guard at PMCC and add a "Systematic & Capital-Efficient Plays" subsection; (4) add one Quality Standards rule gating long-vol to low IV. No schema change — verified all outlooks map to the existing `{BULLISH,BEARISH,NEUTRAL,INCOME,HEDGE}` enum, so no `trade_schemas.py` edit / proxy resync / `schema_version` bump.

**Tech Stack:** Markdown prompt files. No build/lint/test harness exists (per CLAUDE.md); verification is by `grep` and inspection, plus confirming the Pinecone schema enum in `scripts/trade_schemas.py` is untouched.

**Spec deviation note:** The spec ("Changes" §2) said "add two matrix rows." Implementing as in-place row *modifications* instead, because the matrix already has rows for the `LONG / BUY / Low IV` and `FLAT / BUY / High IV` cells and duplicate-key rows would break the "pick THE primary" determinism the routine relies on. Design intent (PMCC/Wheel selectable as primaries) is preserved.

**Install reminder:** Edits to this file do nothing live until `./install.sh` copies it into `~/.claude/skills/`. Run it after the final commit to test in a Claude Code session. No `install.sh`/`uninstall.sh` array change is needed — `trade-options` is already registered.

---

### Task 1: Add four rows to the Neutral/Volatility strategy table

**Files:**
- Modify: `skills/trade-options/SKILL.md` (the `### Neutral Strategies` table, currently ~lines 167–174)

- [ ] **Step 1: Apply the edit**

Replace this exact block:

```markdown
### Neutral Strategies
| Strategy | When to Use | Max Profit | Max Loss | Breakeven |
|----------|-------------|------------|----------|-----------|
| Iron Condor | High IV + range-bound | Net credit | Width - credit | Between short strikes +/- credit |
| Short Strangle | Very high IV + range-bound (undefined risk) | Total credit | Unlimited | Strikes +/- credit |
| Iron Butterfly | High IV + pinning near strike | Net credit | Width - credit | Center +/- credit |
| Covered Call | Own shares + high IV | Premium + upside to strike | Stock downside | Purchase price - premium |
| Calendar Spread | IV term structure steep | Variable | Net debit | Near short strike at front expiration |
```

with:

```markdown
### Neutral & Volatility Strategies
| Strategy | When to Use | Max Profit | Max Loss | Breakeven |
|----------|-------------|------------|----------|-----------|
| Long Straddle | Very low IV + expect big move, direction unknown | Unlimited | Both premiums paid | Strike +/- total premium |
| Long Strangle | Low IV + expect big move, cheaper than straddle | Unlimited | Both premiums paid | Strikes +/- total premium |
| Short Straddle | Very high IV + pin expected (undefined risk) | Total credit | Unlimited | Strike +/- credit |
| Iron Condor | High IV + range-bound | Net credit | Width - credit | Between short strikes +/- credit |
| Short Strangle | Very high IV + range-bound (undefined risk) | Total credit | Unlimited | Strikes +/- credit |
| Iron Butterfly | High IV + pinning near strike | Net credit | Width - credit | Center +/- credit |
| Covered Call | Own shares + high IV | Premium + upside to strike | Stock downside | Purchase price - premium |
| Covered Strangle | LONG + high IV + range-bound + willing to add shares | Credit + upside to call strike | Stock downside + put assignment | Complex (two breakevens) |
| Calendar Spread | IV term structure steep | Variable | Net debit | Near short strike at front expiration |
```

- [ ] **Step 2: Verify the rows landed**

Run: `grep -nE "Long Straddle|Long Strangle|Short Straddle|Covered Strangle" skills/trade-options/SKILL.md`
Expected: four matching lines, all inside the Neutral & Volatility table.

- [ ] **Step 3: Verify column count is intact**

Run: `grep -n "Long Straddle" skills/trade-options/SKILL.md`
Expected: the row has exactly five `|`-delimited cells (Strategy / When / Max Profit / Max Loss / Breakeven). Eyeball that the pipes line up with the header.

- [ ] **Step 4: Commit**

```bash
git add skills/trade-options/SKILL.md
git commit -m "feat(options): add long/short straddle, long strangle, covered strangle to neutral table"
```

---

### Task 2: Make PMCC and the Wheel selectable primaries in the matrix

**Files:**
- Modify: `skills/trade-options/SKILL.md` (the primary-strategy matrix, currently ~lines 130–140)

- [ ] **Step 1: Modify the LONG / BUY / Low IV row (PMCC)**

Replace this exact line:

```markdown
| LONG | STRONG BUY / BUY | Low IV (rank <50) | Hold shares / Call Diagonal | BULLISH | grow, don't cap a cheap-IV runner |
```

with:

```markdown
| LONG | STRONG BUY / BUY | Low IV (rank <50) | Hold / Call Diagonal (≥100 sh) · PMCC (<100 sh) | BULLISH | grow; PMCC is the capital-efficient substitute when share count is small |
```

- [ ] **Step 2: Modify the FLAT / BUY / High IV row (the Wheel)**

Replace this exact line:

```markdown
| FLAT | STRONG BUY / BUY | High IV | Cash-Secured Put | INCOME | grow, get paid to enter |
```

with:

```markdown
| FLAT | STRONG BUY / BUY | High IV | Cash-Secured Put → the Wheel | INCOME | grow; systematic CSP→CC income rotation |
```

- [ ] **Step 3: Verify both rows changed and the matrix still has 9 data rows**

Run: `grep -nE "PMCC \(<100 sh\)|Cash-Secured Put → the Wheel" skills/trade-options/SKILL.md`
Expected: two matching lines (the modified matrix rows).

Run: `awk '/\| Position \| Composite signal/{f=1} f&&/^\| (LONG|FLAT) \|/{c++} END{print c}' skills/trade-options/SKILL.md`
Expected: `9` (no rows added or dropped — only two cells rewritten).

- [ ] **Step 4: Commit**

```bash
git add skills/trade-options/SKILL.md
git commit -m "feat(options): wire PMCC and the Wheel as primary-matrix selections"
```

---

### Task 3: Point the sub-100-share guard at PMCC and add the systematic-plays subsection

**Files:**
- Modify: `skills/trade-options/SKILL.md` (the position-sizing guard at ~line 148–149, and insert a new subsection before `### Bullish Strategies`)

- [ ] **Step 1: Update the sub-100-share guard**

Replace this exact block:

```markdown
- If LONG but `POSITION_SHARES < 100`, covered calls aren't available — fall
  back to the FLAT row's directional/defined-risk play and say why.
```

with:

```markdown
- If LONG but `POSITION_SHARES < 100`, covered calls aren't available — fall
  back to a **PMCC** (the capital-efficient covered-call substitute; see
  "Systematic & Capital-Efficient Plays") or, if rounding up to 100 shares is
  preferred, the FLAT row's directional/defined-risk play. Say which and why.
```

- [ ] **Step 2: Insert the new subsection**

Find this exact line (the heading that opens the directional tables):

```markdown
### Bullish Strategies
```

Insert the following block **immediately before** it (leave one blank line between the new block and `### Bullish Strategies`):

```markdown
### Systematic & Capital-Efficient Plays

Two strategies span multiple legs or trades over time, so the one-row tables
below can't capture them. Recommend them as the PRIMARY when the matrix points
there, and spell out the full sequence in the report.

**Poor Man's Covered Call (PMCC).** A long-dated, deep-ITM call (~80 delta,
6–12 months out) stands in for 100 shares; sell a near-term OTM call against it,
exactly as in a covered call. Far cheaper than buying 100 shares, but it pays no
dividend and the long call bleeds theta. Rules: the long call's strike must sit
far enough below the short call that the spread width covers assignment; watch
early-assignment / ex-dividend risk on the short leg; roll the short call for
income while holding the long-dated anchor. Use it for LONG names with fewer
than 100 shares, or to open a bullish position with less capital.

**The Wheel.** A systematic INCOME rotation: sell a cash-secured put on a name
you'd be content to own → if assigned, take the 100 shares → sell covered calls
against them → if called away, return to selling cash-secured puts. Best in
elevated-IV, range-bound, fundamentally-acceptable names. The Cash-Secured Put
(entry leg) and Covered Call (exit leg) rows give the per-leg risk/reward.

```

- [ ] **Step 3: Verify both edits**

Run: `grep -nE "see\\s+\"Systematic & Capital-Efficient Plays\"|### Systematic & Capital-Efficient Plays|Poor Man's Covered Call \(PMCC\)\.|^\*\*The Wheel\.\*\*" skills/trade-options/SKILL.md`
Expected: the guard reference, the new heading, and both bold strategy lead-ins all match.

Run: `grep -n "### Systematic & Capital-Efficient Plays" skills/trade-options/SKILL.md && grep -n "### Bullish Strategies" skills/trade-options/SKILL.md`
Expected: the systematic-plays heading's line number is smaller than the Bullish heading's (it sits before it).

- [ ] **Step 4: Commit**

```bash
git add skills/trade-options/SKILL.md
git commit -m "feat(options): add Systematic & Capital-Efficient Plays section; PMCC fallback for <100 shares"
```

---

### Task 4: Add the long-volatility IV-justification Quality Standard

**Files:**
- Modify: `skills/trade-options/SKILL.md` (the `## Quality Standards` list, currently ending at rule 8 ~line 477)

- [ ] **Step 1: Apply the edit**

Replace this exact block (rule 8, the last list item):

```markdown
8. **Frontmatter honesty.** Omit any frontmatter line whose value is genuinely unavailable rather than writing a placeholder — but `strategy_outlook`, `recommended_strategy`, and `position_bias` are always required (they're decisions, not data lookups).
```

with:

```markdown
8. **Frontmatter honesty.** Omit any frontmatter line whose value is genuinely unavailable rather than writing a placeholder — but `strategy_outlook`, `recommended_strategy`, and `position_bias` are always required (they're decisions, not data lookups).
9. **Long volatility must be IV-justified.** Long straddles/strangles are premium-buying plays — recommend them only when IV rank is low / very-low (never buy expensive volatility). Short straddle and covered strangle are undefined-risk on at least one side and MUST carry the risk warning required by rule 3.
```

- [ ] **Step 2: Verify**

Run: `grep -n "Long volatility must be IV-justified" skills/trade-options/SKILL.md`
Expected: one match, numbered `9.`, directly after rule 8.

- [ ] **Step 3: Commit**

```bash
git add skills/trade-options/SKILL.md
git commit -m "feat(options): require IV justification for long-vol; reinforce undefined-risk warning"
```

---

### Task 5: Confirm no schema impact, then install

**Files:**
- Read-only check: `scripts/trade_schemas.py`
- Run: `./install.sh`

- [ ] **Step 1: Confirm the outlook enum is untouched**

Run: `grep -nE "BULLISH|BEARISH|NEUTRAL|INCOME|HEDGE" scripts/trade_schemas.py | grep -E '= "'`
Expected: exactly the five enum members (`BULLISH/BEARISH/NEUTRAL/INCOME/HEDGE`) — unchanged. Every new strategy maps to one of these (straddles/strangles → NEUTRAL, PMCC → BULLISH, Wheel + covered strangle → INCOME), so no edit, no `schema_version` bump, no `sync_proxy_schemas.sh`.

- [ ] **Step 2: Sanity-read the edited regions**

Read `skills/trade-options/SKILL.md` and confirm: the Neutral & Volatility table has 9 data rows with aligned pipes; the matrix has 9 data rows; the Systematic & Capital-Efficient Plays subsection sits before `### Bullish Strategies`; Quality Standards ends at rule 9.

- [ ] **Step 3: Install into ~/.claude so the change is live**

Run: `./install.sh`
Expected: success output listing `trade-options` among the copied skills.

- [ ] **Step 4: Commit any remaining staged docs (plan/spec) if not already committed**

```bash
git add docs/superpowers
git commit -m "docs(options): spec + plan for strategy coverage extension"
```

---

## Self-Review

**Spec coverage:**
- Spec §1 (Neutral table: long straddle, long strangle, short straddle, covered strangle) → Task 1. ✓
- Spec §2 (matrix: PMCC + Wheel as primaries, guard tweak) → Task 2 (matrix) + Task 3 Step 1 (guard). ✓ (implemented as in-place row modification — deviation documented above.)
- Spec §3 (Systematic & Capital-Efficient Plays subsection: PMCC + Wheel mechanics) → Task 3 Step 2. ✓
- Spec §4 (Quality Standard: long-vol IV justification + undefined-risk warning) → Task 4. ✓
- Spec "Schema impact: NONE" → Task 5 Step 1 verifies. ✓
- Spec "Out of scope / unchanged" (frontmatter, data collection, output format) → no task touches them. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases"; every edit step shows the exact before/after text. ✓

**Type/name consistency:** Strategy names are spelled identically across tasks — "PMCC" / "Poor Man's Covered Call (PMCC)", "the Wheel", "Covered Strangle", "Long Straddle", "Long Strangle", "Short Straddle". The matrix cell `PMCC (<100 sh)` (Task 2) and the guard reference to PMCC (Task 3) both point at the same "Systematic & Capital-Efficient Plays" heading created in Task 3. ✓
