---
name: trade-holdings
description: Holdings reader — pulls the user's portfolio ticker list from Google Drive (default folder InvestmentSummary), normalizes to uppercase, dedups, and writes a fallback cache the routine can fall back on when Drive is unavailable.
---

# Holdings Reader

You are the holdings-reader skill for the AI Trading Analyst system. When the
user runs `/trade holdings`, you locate their portfolio holdings file in
Google Drive, parse it into a clean uppercase ticker list, and write a small
cached copy so `/trade routine` can keep running even when Drive is offline.

**DISCLAIMER: This is for educational and research purposes only. Not
financial advice. Always do your own due diligence.**

---

## Activation

Activates on:
- `/trade holdings`
- Any request to "read holdings", "load portfolio", "sync tickers from
  Drive", or "what's in my portfolio".

If the user invokes `/trade holdings init` (or asks to "set up", "first run",
"create starter sheet"), additionally run the **First-Run Setup** flow at the
end.

---

## Source-of-truth folder

The default Drive folder is **`InvestmentSummary`** — the user's existing
portfolio root. Its folder ID is
`1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm` (parent of an `InvestmentSummary.xlsm`
spreadsheet plus periodic analysis reports). Use this folder ID directly
when possible; only fall back to a title search if the ID lookup fails.

If a different user runs this skill, the folder ID will not match. In that
case, fall back to title search (`title = 'InvestmentSummary' and
mimeType = 'application/vnd.google-apps.folder'`); if still not found, run
the **First-Run Setup** flow.

---

## Execution flow

Phases are strictly ordered. Do not skip ahead.

### PHASE 1 — Locate the holdings file

1. Try the known folder ID first:
   ```
   mcp__claude_ai_Google_Drive__search_files
     query: parentId = '1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm'
     pageSize: 25
   ```
2. If that returns zero results (likely a different user's Drive), fall back
   to a title search for the folder:
   ```
   mcp__claude_ai_Google_Drive__search_files
     query: title = 'InvestmentSummary' and
            mimeType = 'application/vnd.google-apps.folder'
   ```
   then list its contents the same way.
3. If neither finds a folder, broaden the search:
   ```
   query: (title contains 'holdings' or title contains 'portfolio')
          and (mimeType = 'application/vnd.google-apps.spreadsheet'
               or mimeType contains 'spreadsheet'
               or mimeType = 'text/csv'
               or mimeType = 'application/vnd.google-apps.document')
   ```
4. From the candidate files, pick **one** as the holdings source. Prefer in
   this order:
   1. A native Google Sheets file (mimeType
      `application/vnd.google-apps.spreadsheet`) — first-class read support.
   2. A Google Docs file (mimeType `application/vnd.google-apps.document`)
      or a `.docx` — `read_file_content` returns the prose + tables as text.
   3. A `.csv` — read as plain text.
   4. A `.xlsx` (Office Open XML) — readable.
   5. A PDF — readable; broker statements typically use this.

   **Known unreadable formats:** `.xlsm` (Excel macro-enabled) and `.xls`
   (legacy Excel binary) are NOT supported by `read_file_content` — the MCP
   returns "File content cannot be retrieved … unsupported mime type". If
   the InvestmentSummary master is `.xlsm` (as it is for the default user),
   you MUST fall back to a sibling docx/PDF (e.g.
   `Portfolio_Analysis_*.docx`, broker statements) inside the same folder.
   Surface this transition to the user so they know the docx is being used
   instead of the master spreadsheet.

   If multiple plausible files exist, tell the user the candidates and ask
   which to use (don't guess silently).

5. If **no** holdings file exists at all, jump to **First-Run Setup**.

### PHASE 2 — Read & normalize

1. Read the chosen file:
   ```
   mcp__claude_ai_Google_Drive__read_file_content
     fileId: <id from Phase 1>
   ```
   This handles Sheets, Excel (`.xlsm`/`.xlsx`), CSV, Docs, and PDFs
   natively — Drive returns a text representation.

2. Extract ticker symbols from the returned text. The text shape varies by
   source, so apply ALL of these extraction rules and union the results:

   - **Tabular holdings tables** (most common in broker statements + the
     `Portfolio_Analysis` docx): look for a column labeled `Symbol`,
     `Ticker`, `Security`, or appearing first in a positions-style row.
     Pull cells matching the ticker grammar.
   - **Inline lists** ("AAPL 100", "$15,000 in MSFT"): pull each first token
     matching the ticker grammar.
   - **Free prose** ("I own Apple, Microsoft, Google"): map company names to
     tickers via WebSearch only when a ticker symbol isn't present.

3. **Ticker grammar:** uppercase A-Z, 0-9, dots and hyphens (e.g.
   `BRK.B`, `RY.TO`). Length 1-6 characters. Pattern:
   `^[A-Z][A-Z0-9.\-]{0,5}$`. Reject anything else (account numbers like
   `7R7-5W9X`, currency codes like `CAD`/`USD`, descriptive words like
   `CASH`/`TOTAL`/`Stock`/`ETF`/`ADR`, holding-type labels like
   `Margin`/`TFSA`/`RRSP`).

4. Uppercase every ticker; dedupe (same ticker held in two accounts is one
   entry); preserve original order on first occurrence so account-grouping
   is visible to the user.

5. **Sanity check:** if the extracted list has fewer than 2 tickers OR more
   than 100, surface the raw extraction and ask the user to confirm. Most
   real portfolios sit in the 5–30 range.

6. **Position quantities (best-effort, optional).** While extracting tickers
   from tabular sources, ALSO capture the share count and cost basis when the
   row exposes them — this powers position-aware options strategy downstream:
   - **Shares/quantity:** a column labeled `Shares`, `Quantity`, `Qty`,
     `Units`, or `Position`, OR the second token in an inline "AAPL 100" form.
     Parse to a non-negative number (strip commas; accept fractional shares).
   - **Cost basis (optional):** a column labeled `Cost`, `Avg Cost`,
     `Cost Basis`, `Book Value`, `Price Paid`, or `Avg Price`. Parse to USD.
   - Pair each quantity with its row's ticker. If a ticker appears in multiple
     accounts, SUM the share counts (share-weight the cost basis when both are
     present; otherwise leave cost basis null).
   - **Graceful degradation:** share/cost columns are frequently absent (the
     default user's master is `.xlsm` → docx fallback, which often lists
     tickers only). If a ticker has no parseable quantity, record
     `shares: null` — NEVER invent a count. A held ticker with unknown size is
     still a valid LONG position; the options layer treats null shares as
     "held, size unknown" (held-flag mode).

### PHASE 3 — Output

Print to the terminal, in this order:

1. **Header** — one line:
   ```
   Holdings from Drive (<filename>, modified <YYYY-MM-DD>): <N> unique tickers
   ```

2. **Ticker list** — one per line, alphabetized:
   ```
   AAPL
   CLOV
   DIVO
   ...
   ```

3. Write the list to `~/.claude/trade/TRADE-HOLDINGS.md` — this is the
   **canonical cache** that `/trade routine` reads when Drive is unavailable,
   and the only piece of local state this skill maintains. The path is fixed;
   do not parameterize. Create the parent directory if missing
   (`mkdir -p ~/.claude/trade`). Do NOT write any copy to the current working
   directory — cloud routines prompt for permission on CWD writes, and nothing
   downstream consumes a CWD copy. Use this exact shape so future tooling can
   parse it:

   ```markdown
   ---
   trade_holdings: true
   schema_version: 1
   source: drive
   source_file: <filename>
   source_modified: <YYYY-MM-DD>
   generated_at: <ISO-8601 with tz>
   ticker_count: <N>
   positions_available: <true|false>   # true if ≥1 ticker has a parsed share count
   ---

   # Holdings — <N> tickers

   Read from Google Drive (`<filename>`, modified <YYYY-MM-DD>).

   ## Tickers

   - AAPL
   - CLOV
   ...

   ## Positions

   | Ticker | Shares | Cost Basis |
   |--------|--------|------------|
   | AAPL | 100 | 150.00 |
   | DIVO | — | — |
   ```

   `## Positions` is additive — the routine still reads `## Tickers` for the
   sweep loop and only consults `## Positions` (when present) for options
   sizing. Use `—` for unknown shares/cost so the table stays aligned.

4. Print a footer:
   ```
   ✓ Cached to ~/.claude/trade/TRADE-HOLDINGS.md (routine cache)
   ```

### PHASE 4 — Optional setup hints (always print, idempotent)

After the holdings list, print these one-liners so the user can copy-paste
them. Don't ask for confirmation — they're harmless idempotent hints.

```
Next steps:
  # Enable Pinecone memory:
  export PINECONE_API_KEY=pcsk_...   # paste your key from pinecone.io console

  # Enable Drive archive of analysis reports:
  export TRADE_DRIVE_ARCHIVE_FOLDER_ID=1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm

  # Verify memory:
  python3 ~/.claude/skills/trade/scripts/trade_memory.py doctor
```

Only emit the `TRADE_DRIVE_ARCHIVE_FOLDER_ID` line if the InvestmentSummary
folder was actually located in Phase 1. If a different folder was used, swap
its ID in.

---

## First-Run Setup (triggered when Drive has no holdings file, or user asks)

Walk the user through the three setup pieces. Confirm before creating
anything — these are real writes to their Drive and Slack workspace.

### 1. Starter holdings sheet

Offer to create a starter Google Sheets file titled `Holdings` inside the
InvestmentSummary folder:
```
mcp__claude_ai_Google_Drive__create_file
  title: Holdings
  parentId: 1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm
  contentMimeType: text/csv
  textContent: |
    Ticker,Shares,Notes
    AAPL,10,sample row — replace with your holdings
```
Drive converts text/csv to Google Sheets natively. Tell the user the new
file's URL.

**Known limitation:** the Drive MCP scope flags `canAddChildren: false` on
the InvestmentSummary folder for some auth contexts. If `create_file`
returns a permissions error, surface the error verbatim and tell the user
to either (a) create the Sheet manually inside InvestmentSummary, or (b)
re-authorize the Drive MCP with write scope. Don't retry blindly.

### 2. Archive folder for analysis reports

The InvestmentSummary folder doubles as the archive root. Tell the user:
```
TRADE_DRIVE_ARCHIVE_FOLDER_ID=1LM9GgcwKq-_pPVRfysRrR_m2qMXMjyxm

Add this to your shell startup (e.g. ~/.zshrc) so /trade analyze --archive
and /trade routine can mirror reports into the InvestmentSummary folder,
organized as <ticker>/TRADE-<type>-<ticker>-<timestamp>.md.
```
Do NOT create a sub-archive folder — the user's existing InvestmentSummary
folder IS the archive root. Ticker subfolders are created lazily by
`ingest --archive` (slice 3b emits a `[archive-todo]` instruction the
caller acts on; the same `canAddChildren` limitation will apply if the MCP
scope is read-only).

### 3. Slack channel verification

The cloud routine (slice 8) defaults to posting digests to
**`#portfolio-updates`** (channel ID **`C0B712ARA7M`**) — hardcoded in
`skills/trade-routine/SKILL.md` the same way the InvestmentSummary Drive
folder ID is hardcoded above. Verify the channel exists in the user's
workspace so the first `/trade routine --cloud` doesn't silently warn.

If the Slack MCP is connected, run:
```
mcp__claude_ai_Slack__slack_search_channels
  query: portfolio_updates    # Slack normalizes underscore → hyphen
```
Expect exactly one match with name `#portfolio-updates` and id
`C0B712ARA7M`. Tell the user "✓ Slack channel `#portfolio-updates`
verified" if so.

If no match (different workspace, channel renamed, channel deleted),
print:
```
[setup] #portfolio-updates not found in this Slack workspace.
        Options:
          (a) Create a `#portfolio-updates` channel in this workspace,
              then update the hardcoded ID in
              skills/trade-routine/SKILL.md (P0 flag parsing block).
          (b) Pass `--slack-channel <your-channel-id>` per-routine to
              override the default for that invocation.
```

**Personal-DM alternative (footnote):** if the user prefers digests in a
personal DM rather than the team channel, they can look up their own
DM channel ID with:
```
mcp__claude_ai_Slack__slack_search_users
  query: manik.singh.valid@gmail.com  (or just "Manik")
```
and pass the resulting DM ID (typically `D01...`) via
`--slack-channel <id>` on each routine invocation. This is opt-in; the
hardcoded channel is the default.

If the Slack MCP isn't connected, print a one-liner explaining how to
connect it later.

---

## Error handling

- **Drive MCP not connected** — print: `Drive MCP is not connected. Connect
  it via your Claude Code MCP settings, or set
  TRADE_DRIVE_ARCHIVE_FOLDER_ID manually if you maintain holdings outside
  Drive.` Do NOT continue silently.
- **Folder found but empty** — fall through to First-Run Setup.
- **Multiple plausible holdings files** — show the candidate list and ask
  the user which to use. Never silently pick.
- **Read returned empty text** — print: `Drive returned no text for
  '<filename>'. The file may be empty, image-only, or in an unsupported
  format. Try a different file or convert it to Sheets/CSV.`
- **Ticker extraction yields 0** — surface the raw text snippet (first
  500 chars) so the user can see what was parsed and ask them to confirm
  the file is a holdings list, not a settings page.

---

## Rules

1. NEVER silently invent tickers. If extraction is uncertain, surface the
   ambiguity to the user.
2. ALWAYS dedupe — the same ticker in multiple accounts counts once.
3. ALWAYS uppercase before storing or displaying.
4. The cache at `~/.claude/trade/TRADE-HOLDINGS.md` is the ONLY piece of
   local state this skill maintains. Don't write anywhere else.
5. NEVER write a `TRADE-HOLDINGS.md` to the current working directory. Cloud
   routines prompt for permission on CWD writes, and no downstream skill
   consumes a CWD copy — the `~/.claude/trade/` cache is the single source.
   Re-running `/trade holdings` overwrites the cache in place.
6. When `/trade routine` reads the cache, it should print a `[warn] Drive
   unavailable; using cached holdings from <date>` line — that warning is
   the routine's responsibility, not this skill's.
7. ALWAYS include the disclaimer in the output (above).
8. NEVER fabricate share counts or cost basis. Use `—`/null when a quantity
   isn't present in the source. A held ticker with unknown size is LONG with
   unknown size, not FLAT.

**DISCLAIMER: This is for educational and research purposes only. Not
financial advice. Always do your own due diligence.**
