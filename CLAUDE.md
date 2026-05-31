# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

This is the **source** for a Claude Code plugin — a suite of trading-research skills and subagents. Almost every file is a Markdown *prompt* (SKILL.md / agent definitions), not application code. The only executable is `scripts/generate_trade_pdf.py`.

It is a research/analysis tool: given a ticker, it gathers public data via WebSearch/WebFetch and produces scored analysis. It does **not** connect to brokerages, use market-data APIs/keys, or execute trades. Every output must carry the educational/not-financial-advice disclaimer.

**Editing files here does nothing to the live tool until you run `./install.sh`**, which copies sources into `~/.claude/`:
- `trade/SKILL.md` + `skills/<name>/SKILL.md` → `~/.claude/skills/`
- `agents/<name>.md` → `~/.claude/agents/`
- `scripts/*.py` → `~/.claude/skills/trade/scripts/`

So to test a change to a skill/agent, re-run `./install.sh`, then invoke the command in a Claude Code session. There is no build step, linter, or test suite.

## Commands

```bash
./install.sh                              # Install skills/agents/scripts into ~/.claude (re-run to update)
./uninstall.sh                            # Remove them from ~/.claude
pip3 install reportlab                    # Only dependency, only needed for PDF generation

# Exercise the PDF generator directly:
python3 scripts/generate_trade_pdf.py                          # DEMO mode → writes TRADE-REPORT-sample.pdf
python3 scripts/generate_trade_pdf.py data.json TRADE-REPORT.pdf   # Real data from a JSON payload
```

## Architecture

`trade/SKILL.md` is the **orchestrator / command router**. It maps `/trade <command> <args>` to one of the sub-skills in `skills/`. Each sub-skill is a self-contained prompt that gathers data and writes a Markdown report (`TRADE-<TYPE>-<TICKER>.md`) to the current working directory.

The flagship `/trade analyze` (in `skills/trade-analyze/SKILL.md`) runs a strict **3-phase** flow:
1. **Discovery** — the orchestrator itself gathers shared baseline data (price, financials, news) into a `DISCOVERY_BRIEF`, so the agents don't redundantly re-search it.
2. **Parallel fan-out** — launches **all 5 subagents in a single message** (technical, fundamental, sentiment, risk, thesis), each receiving the brief plus a specialized mandate. Launching them together is the whole point; never serialize them.
3. **Synthesis** — combines the 5 returned scores into a weighted composite, derives grade + signal, and writes the unified report.

The 5 files in `agents/` are the subagent definitions for that fan-out. Note `skills/trade-technical/` etc. (single-dimension command) and `agents/trade-technical.md` (subagent invoked by `analyze`) are *related but distinct* prompts — keep their methodology consistent.

## Cross-file contracts (the easy things to break)

- **Scoring weights are duplicated across files and must stay in sync.** Technical 25% / Fundamental 25% / Sentiment 20% / Risk 15% / Thesis 15%, and the composite formula, appear in `README.md`, `trade/SKILL.md`, `skills/trade-analyze/SKILL.md`, **and** the `**Weight:**` header of each `agents/*.md`. Change one → change all. The same applies to the score→grade→signal table (85+/A+/Strong Buy … 0-24/F/Avoid).
- **`install.sh` hardcodes the file lists.** Adding a skill or agent requires also adding its name to the `SKILLS=(…)` or `AGENTS=(…)` array in `install.sh` (and the command-reference echo block), or it won't be installed. The README "All 16 Commands" / project-structure section should be updated too.
- **Risk score is inverted**: higher = lower risk, so it composes correctly into the weighted total. Preserve that convention in `agents/trade-risk.md` and `trade-analyze`.

## Conventions

- **Every skill and agent needs YAML `name`/`description` frontmatter** — that's how Claude Code discovers and routes to them. All current `skills/*/SKILL.md`, the `trade/` orchestrator, and all `agents/*.md` have it; any new skill/agent must too, or it won't register.
- **Agent files keep their custom header *after* the frontmatter** — `# <Name> Agent` plus `**Weight:**` / `**Output:**` / disclaimer lines. Preserve that shape (the `**Weight:**` line is part of the scoring contract above).
- **Output filenames**: `TRADE-ANALYSIS-<TICKER>.md`, `TRADE-TECHNICAL-<TICKER>.md`, etc., always written to CWD. PDF is `TRADE-REPORT.pdf`. These patterns are git-ignored (see `.gitignore`).
- Prompts mandate: cite specific numbers (never fabricate — say "Data not available"), always give both bull and bear cases, timestamp the analysis, and end with the disclaimer.

## PDF generator gotcha

`skills/trade-report-pdf/SKILL.md` instructs writing the payload to `/tmp/trade_report_data.json` and running the script **with no arguments** — but the script with no args runs **demo mode** and ignores that file. To render real data you must pass the JSON path as the first CLI argument: `python3 …/generate_trade_pdf.py /tmp/trade_report_data.json TRADE-REPORT.pdf`. The script reads a single JSON payload aggregating all discovered `TRADE-*.md` analyses; its expected schema is documented in that skill's Step 2/3.
