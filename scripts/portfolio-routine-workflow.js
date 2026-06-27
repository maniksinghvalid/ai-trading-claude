export const meta = {
  name: 'portfolio-routine',
  description: 'Daily portfolio routine: 14-ticker analyze sweep + AutoTrader webhook delivery',
  phases: [
    {title: 'Analyze', detail: 'Run 5-dimension analysis for all 14 tickers in parallel'},
    {title: 'Deliver', detail: 'Build payload, fire webhook, post to Slack, upload to Drive'},
  ]
}

// ─── Args (passed by scheduled automation) ────────────────────────────────────
// args.run_id     — e.g. 'routine-20260627-0500-abc123'
// args.date       — e.g. '2026-06-27'
// args.dateLabel  — e.g. 'June 27, 2026'
// args.digestFile — e.g. 'TRADE-ROUTINE-20260627-0500.md'
// args.priors     — { CLOV: 'HOLD', DIVO: 'BUY', ... } (prior signals per ticker;
//                    used as FALLBACK only — STEP 0 recalls the authoritative prior
//                    signal/score per ticker from Pinecone and that wins when present)
// args.secrets    — { pineconeProxyToken, vercelBypass, webhookSecret, pineconeProxyUrl?, webhookUrl? }
//                    injected at runtime by the routine prompt (held in RemoteTrigger config,
//                    NOT committed). The workflow runtime has no process.env, so args is the
//                    only injection point. NEVER hardcode these tokens in this file.
// All have fallbacks so the script can also be test-invoked without args.

const RUN_ID      = (args && args.run_id)     ? args.run_id     : 'routine-unknown'
const DATE        = (args && args.date)       ? args.date       : '1970-01-01'
const DATE_LABEL  = (args && args.dateLabel)  ? args.dateLabel  : DATE
const DIGEST_FILE = (args && args.digestFile) ? args.digestFile : ('TRADE-ROUTINE-' + DATE.replace(/-/g,'') + '.md')
const PRIORS      = (args && args.priors)     ? args.priors     : {}

const CWD = '/home/user/ai-trading-claude'
// Secrets injected via args.secrets (see header). Non-secret URLs keep a default;
// the three tokens default to '' and MUST be supplied by the routine prompt at runtime.
const SECRETS        = (args && args.secrets) || {}
const PROXY_URL      = SECRETS.pineconeProxyUrl   || 'https://www.mga-pservices.cloud'
const PROXY_TOKEN    = SECRETS.pineconeProxyToken || ''
const VERCEL_BYPASS  = SECRETS.vercelBypass       || ''
const WEBHOOK_URL    = SECRETS.webhookUrl         || 'https://unthawed-keshia-unplenteously.ngrok-free.dev'
const WEBHOOK_SECRET = SECRETS.webhookSecret      || ''

const PINECONE_ENV = `export PINECONE_PROXY_URL='${PROXY_URL}'
export PINECONE_PROXY_TOKEN='${PROXY_TOKEN}'
export VERCEL_PROTECTION_BYPASS='${VERCEL_BYPASS}'
export TRADE_RUN_ID='${RUN_ID}'
cd /home/user/ai-trading-claude`

// ─── Holdings — prior signals come from args.priors (default: NEUTRAL) ────────
const HOLDINGS = [
  {ticker:'CLOV',  company:'Clover Health Investments, Inc.',                         assetType:'stock',  searchHint:'CLOV stock'},
  {ticker:'DIVO',  company:'Amplify CWP Enhanced Dividend Income ETF',                assetType:'etf',    searchHint:'DIVO ETF'},
  {ticker:'IAU',   company:'iShares Gold Trust',                                       assetType:'etf',    searchHint:'IAU gold ETF'},
  {ticker:'IBIT',  company:'iShares Bitcoin Trust ETF',                               assetType:'etf',    searchHint:'IBIT bitcoin ETF'},
  {ticker:'MARA',  company:'MARA Holdings Inc (Bitcoin miner)',                        assetType:'stock',  searchHint:'MARA stock bitcoin mining'},
  {ticker:'NIO',   company:'NIO Inc. (Chinese EV)',                                    assetType:'stock',  searchHint:'NIO stock EV'},
  {ticker:'O',     company:'Realty Income Corporation',                                assetType:'reit',   searchHint:'Realty Income O REIT'},
  {ticker:'SCHF',  company:'Schwab International Equity ETF',                          assetType:'etf',    searchHint:'SCHF ETF international'},
  {ticker:'SPCE',  company:'Virgin Galactic Holdings',                                 assetType:'stock',  searchHint:'SPCE Virgin Galactic stock'},
  {ticker:'VDY',   company:'Vanguard FTSE Canadian High Dividend Yield Index ETF',    assetType:'etf-ca', searchHint:'VDY.TO TSX ETF'},
  {ticker:'XIC',   company:'iShares Core S&P/TSX Capped Composite Index ETF',         assetType:'etf-ca', searchHint:'XIC.TO TSX ETF'},
  {ticker:'XEQT',  company:'iShares Core Equity ETF Portfolio',                        assetType:'etf-ca', searchHint:'XEQT.TO TSX ETF'},
  {ticker:'YNVDA', company:'YieldMax NVDA Option Income Strategy ETF (NVDY)',          assetType:'etf',    searchHint:'NVDY YieldMax ETF'},
  {ticker:'ZAG',   company:'BMO Aggregate Bond Index ETF',                             assetType:'etf-ca', searchHint:'ZAG.TO TSX bond ETF'},
].map(h => ({...h, prior: PRIORS[h.ticker] || 'NEUTRAL'}))

// ─── Schema ───────────────────────────────────────────────────────────────────
const ANALYSIS_SCHEMA = {
  type: 'object',
  required: ['ticker','composite_score','signal','grade','technical_score','fundamental_score','sentiment_score','risk_score','thesis_score'],
  properties: {
    ticker:                {type:'string'},
    company:               {type:'string'},
    composite_score:       {type:'number'},
    signal:                {type:'string', enum:['STRONG BUY','BUY','HOLD','NEUTRAL','CAUTION','AVOID']},
    grade:                 {type:'string', enum:['A+','A','B','C','D','F']},
    technical_score:       {type:'number'},
    fundamental_score:     {type:'number'},
    sentiment_score:       {type:'number'},
    risk_score:            {type:'number'},
    thesis_score:          {type:'number'},
    current_price:         {type:'string'},
    stop_loss:             {type:['number','null']},
    nearest_catalyst_date: {type:['string','null']},
    nearest_catalyst_event:{type:['string','null']},
    memory_hit:            {type:'boolean'},
    prior_signal_recalled: {type:['string','null']},
    prior_score_recalled:  {type:['number','null']},
    file_written:          {type:'boolean'},
    ingest_ok:             {type:'boolean'},
    analysis_summary:      {type:'string'},
  }
}

// ─── Per-ticker analysis prompt ───────────────────────────────────────────────
function buildAnalysisPrompt(h) {
  const caNote = h.assetType === 'etf-ca'
    ? '\nIMPORTANT: This is a Canadian TSX ETF. Search with .TO suffix (e.g., ' + h.ticker + '.TO). Price is in CAD.'
    : ''
  const nvdyNote = h.ticker === 'YNVDA'
    ? '\nIMPORTANT: Portfolio ticker is YNVDA but the actual ETF is NVDY (YieldMax NVDA Option Income Strategy ETF). Search for NVDY. Store results under ticker YNVDA.'
    : ''
  const fundamentalsHint = h.assetType === 'stock'
    ? 'P/E ratio, revenue growth, EPS, balance sheet health'
    : h.assetType === 'reit'
      ? 'FFO yield, payout ratio, occupancy, debt levels'
      : 'AUM, yield, MER, sector/asset exposure, NAV'

  return `You are running a comprehensive 5-dimension trade analysis for ${h.ticker} (${h.company}) as part of the daily portfolio routine on ${DATE_LABEL}.${caNote}${nvdyNote}

PRIOR SIGNAL (caller-provided, last known): ${h.prior}
ANALYSIS DATE: ${DATE_LABEL}

=== STEP 0: RECALL PRIOR ANALYSIS FROM PINECONE (memory seed — do this FIRST, before searching) ===
Pull this ticker's most recent prior ANALYSIS record from vector memory so today's review is continuity-aware:
\`\`\`bash
${PINECONE_ENV}
python3 ~/.claude/skills/trade/scripts/trade_memory.py latest ${h.ticker} --type ANALYSIS 2>/dev/null | tail -40
\`\`\`
Interpret the output:
- A record with composite_score + signal + grade + generated_at (and maybe a thesis/summary) → a prior analysis EXISTS. Note its score, signal, grade, and date. Set memory_hit=true, prior_signal_recalled=<that signal>, prior_score_recalled=<that composite_score>.
- Empty output, "no records"/"not found", or an error (e.g. proxy 403 host_not_allowed → memory unavailable) → NO usable prior. Set memory_hit=false, prior_signal_recalled=null, prior_score_recalled=null, and proceed as a fresh first-time analysis.

Use any recalled prior as CONTEXT, not an anchor: today's web data governs the score, but (a) carry forward durable thesis points that are still valid, and (b) if your new signal diverges materially from a RECENT prior, say so in the body and explain what changed (new catalyst, price move, fundamentals). A large unexplained swing from a recent prior means re-check your inputs.

=== STEP 1: GATHER DATA (use WebSearch) ===
Run 2-3 searches to find:
- Current price, 52-week range, recent performance
- Key metrics: ${fundamentalsHint}
- Recent news (past 7 days) and analyst sentiment
- Upcoming catalysts (earnings dates, events, macro)

Search terms: "${h.searchHint} price ${DATE.slice(0,4)}", "${h.searchHint} news ${DATE_LABEL}", "${h.searchHint} analysis outlook"

=== STEP 2: SCORE ALL 5 DIMENSIONS (0-100 each) ===

TECHNICAL SCORE (25% weight) — Trend, momentum, chart setup:
- 80-100: Strong uptrend, bullish breakout, RSI 50-70
- 60-79: Moderate uptrend, above key MAs
- 40-59: Neutral/mixed signals, ranging
- 20-39: Downtrend, below key MAs
- 0-19: Sharp breakdown, bearish momentum

FUNDAMENTAL SCORE (25% weight) — Quality of underlying business/asset:
- 80-100: Excellent fundamentals, strong growth, wide moat
- 60-79: Good fundamentals, moderate growth
- 40-59: Average, some concerns
- 20-39: Weak fundamentals, deteriorating
- 0-19: Very poor, high failure risk

SENTIMENT SCORE (20% weight) — News tone, analyst consensus, institutional activity:
- 80-100: Very bullish news, upgrades, institutional buying
- 60-79: Mostly positive, bullish bias
- 40-59: Neutral/mixed
- 20-39: Negative bias, downgrades
- 0-19: Extremely negative sentiment

RISK SCORE (15% weight) — INVERTED: HIGHER = LOWER RISK:
- 80-100: Very low risk, stable, liquid
- 60-79: Moderate-low risk
- 40-59: Moderate risk
- 20-39: High risk, volatile
- 0-19: Extreme risk, speculative

THESIS SCORE (15% weight) — Investment case clarity and timing:
- 80-100: Very clear thesis, strong catalysts, good timing
- 60-79: Good thesis, identifiable catalysts
- 40-59: Moderate thesis, mixed timing
- 20-39: Weak thesis, poor timing
- 0-19: No clear thesis

=== STEP 3: COMPUTE COMPOSITE ===
composite_score = round(technical*0.25 + fundamental*0.25 + sentiment*0.20 + risk*0.15 + thesis*0.15)

SIGNAL MAPPING (use EXACT strings; note the space in "STRONG BUY"):
85+ → grade="A+", signal="STRONG BUY"
70-84 → grade="A",  signal="BUY"
55-69 → grade="B",  signal="HOLD"
40-54 → grade="C",  signal="NEUTRAL"
25-39 → grade="D",  signal="CAUTION"
0-24  → grade="F",  signal="AVOID"

=== STEP 4: WRITE TRADE-ANALYSIS FILE ===
Use the Write tool to create /home/user/ai-trading-claude/TRADE-ANALYSIS-${h.ticker}.md

The file MUST start with this EXACT YAML frontmatter (fill in computed values):
---
schema_version: 1
ticker: ${h.ticker}
company: "${h.company}"
report_type: ANALYSIS
generated_at: ${DATE}T00:00:00+00:00
generated_date: ${DATE}
composite_score: <computed integer>
technical_score: <integer>
fundamental_score: <integer>
sentiment_score: <integer>
risk_score: <integer>
thesis_score: <integer>
signal: <exact signal string>
grade: <grade>
price_at_analysis: <current price as float>
stop_loss: <recommended stop-loss as float, or null>
nearest_catalyst_date: <YYYY-MM-DD or null>
catalysts:
  - "<catalyst description 1>"
  - "<catalyst description 2>"
run_id: ${RUN_ID}
source_path: /home/user/ai-trading-claude/TRADE-ANALYSIS-${h.ticker}.md
---

Then write a comprehensive analysis body (400-600 words) organized:
## Trade Analysis: ${h.ticker}
**Date:** ${DATE_LABEL} | **Prior Signal:** ${h.prior} | **Score:** [computed]/100 | **Signal:** [signal] | **Grade:** [grade]
### Technical Analysis
### Fundamental Analysis
### Sentiment & Momentum
### Risk Assessment
### Investment Thesis
### Bull Case (2-3 bullets)
### Bear Case (2-3 bullets)
### Entry/Exit Levels
*DISCLAIMER: Educational and research purposes only. Not financial advice.*

=== STEP 5: INGEST TO PINECONE (non-fatal) ===
Run this bash command (non-zero exit is OK, just log it):
\`\`\`bash
${PINECONE_ENV}
python3 ~/.claude/skills/trade/scripts/trade_memory.py ingest TRADE-ANALYSIS-${h.ticker}.md 2>&1 | tail -5
\`\`\`

=== STEP 6: RETURN STRUCTURED RESULT ===
Return structured JSON with all scores, signal, grade, current_price, stop_loss, nearest_catalyst_date, nearest_catalyst_event.
Set file_written=true if Write tool succeeded, ingest_ok=true if ingest returned exit code 0.
Also include the STEP 0 memory fields: memory_hit (true/false), and prior_signal_recalled / prior_score_recalled (the recalled prior's signal and composite score when memory_hit=true, else null).

Today is ${DATE_LABEL}. Use only real data from web searches.
DISCLAIMER: Educational and research purposes only. Not financial advice.`
}

// ─── Phase 1: 14 parallel analyses ───────────────────────────────────────────
phase('Analyze')
log('Launching 14 parallel ticker analyses for run ' + RUN_ID + '...')

const rawAnalyses = await parallel(HOLDINGS.map(h => () =>
  agent(buildAnalysisPrompt(h), {
    label: 'analyze:' + h.ticker,
    phase: 'Analyze',
    schema: ANALYSIS_SCHEMA,
  })
))

const analyses = rawAnalyses.filter(Boolean)
log(analyses.length + '/14 analyses completed')
const memorySeeded = analyses.filter(a => a.memory_hit).length
log(memorySeeded + '/' + analyses.length + ' analyses seeded with a prior Pinecone record (memory hit)')

if (analyses.length === 0) {
  return {error: 'All 14 analyses failed — nothing to deliver'}
}

const priorByTicker = {}
for (const h of HOLDINGS) { priorByTicker[h.ticker] = h.prior }

// ─── Phase 2: Deliver ─────────────────────────────────────────────────────────
phase('Deliver')

const analysisSummary = analyses.map(a => ({
  ticker:                a.ticker,
  prior_signal:          a.prior_signal_recalled || priorByTicker[a.ticker] || 'NEUTRAL',
  prior_score:           (a.prior_score_recalled ?? null),
  memory_hit:            a.memory_hit || false,
  new_signal:            a.signal,
  composite_score:       a.composite_score,
  grade:                 a.grade,
  current_price:         a.current_price || null,
  stop_loss:             a.stop_loss || null,
  nearest_catalyst_date: a.nearest_catalyst_date || null,
  nearest_catalyst_event:a.nearest_catalyst_event || null,
  file_written:          a.file_written || false,
}))

const filesWritten   = analysisSummary.filter(a => a.file_written).length
const changedSignals = analysisSummary.filter(a => a.new_signal !== a.prior_signal)
log(filesWritten + ' TRADE-ANALYSIS files written')
log(changedSignals.length + ' signal changes: ' + changedSignals.map(a => a.ticker + ':' + a.prior_signal + '->' + a.new_signal).join(', '))

const deliverPrompt = `You are executing Step W (AutoTrader webhook delivery) for portfolio routine ${RUN_ID}.

All analyses have completed. Your job: build the sweep payload, fire the webhook, post to Slack, and upload the digest to Drive.

=== ANALYSIS RESULTS (${analysisSummary.length} tickers) ===
${JSON.stringify(analysisSummary, null, 2)}

=== STEP 1: WRITE /tmp/sweep_inputs.json ===

Rules:
- "rows": ONLY tickers where new_signal != prior_signal. Each: {"ticker":"X","prior_signal":"NEUTRAL","new_signal":"BUY","new_score":71}
- "holdings": ALL tickers. Each: {"ticker":"X","new_signal":"BUY","new_score":71}
- "stops": Tickers with non-null stop_loss. Each: {"ticker":"X","stop_price":1.80}
- "catalysts": Tickers with non-null nearest_catalyst_date. Each: {"ticker":"X","event":"...","date":"YYYY-MM-DD","value":71}

=== STEP 2: RUN build_sweep_payload.py ===
\`\`\`bash
export PINECONE_PROXY_URL='${PROXY_URL}'
export PINECONE_PROXY_TOKEN='${PROXY_TOKEN}'
export VERCEL_PROTECTION_BYPASS='${VERCEL_BYPASS}'
python3 /home/user/ai-trading-claude/scripts/build_sweep_payload.py sweep \\
  --run-id ${RUN_ID} \\
  --in /tmp/sweep_inputs.json \\
  --out /tmp/sweep_payload.json
echo "Exit: $?"
cat /tmp/sweep_payload.json
\`\`\`

If exit non-zero or file missing: post error to Slack and skip webhook.

=== STEP 3: POST PAYLOAD JSON TO SLACK ===
Use mcp__Slack__slack_send_message to channel_id="C0B712ARA7M":
"Portfolio Routine Sweep Payload — ${RUN_ID}\n\`\`\`json\n[FULL JSON]\`\`\`"
If JSON > 3000 chars: use mcp__Slack__slack_create_canvas (title="Sweep Payload ${DATE}").

=== STEP 4: FIRE AUTOTRADER WEBHOOK ===
Sign and POST with TWO headers (X-Webhook-Token AND X-Webhook-Signature):
\`\`\`bash
SECRET='${WEBHOOK_SECRET}'
SIG="sha256=$(openssl dgst -sha256 -hmac "$SECRET" < /tmp/sweep_payload.json | awk '{print $2}')"
HTTP_CODE=$(curl -s -o /tmp/webhook_response.txt -w "%{http_code}" \\
  -X POST \\
  -H "Content-Type: application/json" \\
  -H "X-Webhook-Token: \${SECRET}" \\
  -H "X-Webhook-Signature: \${SIG}" \\
  --data-binary @/tmp/sweep_payload.json \\
  ${WEBHOOK_URL}/webhook/sweep)
echo "HTTP: \${HTTP_CODE}"
cat /tmp/webhook_response.txt
\`\`\`
Expected 202. If 400: bad payload. If 403: egress issue. If 4xx/5xx tunnel may be down.

=== STEP 5: WRITE ROUTINE DIGEST ===
Write /home/user/ai-trading-claude/${DIGEST_FILE}:
\`\`\`markdown
---
run_id: ${RUN_ID}
date: ${DATE}
tickers_analyzed: ${analysisSummary.length}
signal_changes: [count]
webhook_status: [HTTP code or FAILED]
---

# Portfolio Routine — ${DATE_LABEL}

**Run ID:** ${RUN_ID}
**Date:** ${DATE_LABEL} | **Tickers:** ${analysisSummary.length} | **Signal Changes:** [n]

## Sweep Summary

| Ticker | Prior | New Signal | Score | Grade | Note |
|--------|-------|-----------|-------|-------|------|
[one row per ticker; mark changed signals with →]

## Signal Changes
[List changed signals with prior→new and brief rationale]

## Upcoming Catalysts
[catalyst table: Ticker | Date | Event]

## Webhook
[HTTP status and timestamp]

## Stop Losses
[table: Ticker | Stop Price]

*DISCLAIMER: Educational research only. Not financial advice.*
\`\`\`

=== STEP 6: POST DIGEST TO SLACK ===
Read ${DIGEST_FILE}.
- ≤3000 chars: mcp__Slack__slack_send_message to channel_id="C0B712ARA7M"
- >3000 chars: mcp__Slack__slack_create_canvas (channel_id="C0B712ARA7M", title="Portfolio Routine ${DATE}")

=== STEP 7: UPLOAD DIGEST TO DRIVE ===
Use mcp__Google-Drive__create_file:
- title: "${DIGEST_FILE}"
- textContent: [file contents]
- contentMimeType: "text/markdown"
- parentId: "1I4RpHfGS50Ep_qaUi2aTn-CgCB8WDzq_"
- disableConversionToGoogleType: true

=== FINAL REPORT ===
- [✅/❌] Sweep payload built (N signal changes, M holdings)
- [✅/❌] Webhook fired — HTTP [code]
- [✅/❌] Slack payload posted
- [✅/❌] Routine digest written
- [✅/❌] Slack digest posted
- [✅/❌] Drive uploaded

Today is ${DATE_LABEL}. Educational/research only. Not financial advice.`

const delivery = await agent(deliverPrompt, {
  label: 'deliver:step-w',
  phase: 'Deliver',
})

return {
  run_id:           RUN_ID,
  analyses_completed: analyses.length,
  signal_changes:   changedSignals.length,
  delivery_result:  delivery,
}
