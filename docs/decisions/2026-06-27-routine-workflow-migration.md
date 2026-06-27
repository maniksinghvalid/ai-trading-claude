# Daily portfolio routine: prose skill prompt → deterministic Workflow

- **Date:** 2026-06-27
- **Status:** Accepted (live)
- **Scope:** `trade-routine-daily-portfolio-sweep` cloud routine (`trig_01AzqzJSNEqaCLCG6LcGfAt9`, cron `0 11 * * *`)
- **Affected:** `scripts/portfolio-routine-workflow.js`, `scripts/build_sweep_payload.py`; the deployed RemoteTrigger prompt. The separate `trade-options-sweep` job is unchanged.

## Context

This cloud routine runs unattended every day, places real (paper) trades via the
AutoTrader webhook, and writes to Slack / Drive / Pinecone. Reliability and
reproducibility matter more than convenience.

The previous implementation was a long natural-language prompt that asked the cloud
agent to *interpret and hand-execute* every step — load holdings, tier each ticker,
dispatch analyses, build the webhook payload inline, HMAC-sign and POST it, post to
Slack, upload to Drive. Putting the model in charge of orchestration caused recurring,
real problems:

1. **Drift & inconsistency.** The payload builder existed in several prose copies that
   fell out of sync — one shipped options changes with no `overlay` enum (silently
   dropped by the receiver); another used the wrong webhook header
   (`X-Signature-SHA256`) and got a `401`. Model-interpreted steps vary run to run.
2. **No guaranteed structure.** Parallel fan-out, exact field mapping, and validation
   all depended on the agent *remembering* to do them correctly.
3. **Memory was write-only.** Each analysis was generated cold from web search; prior
   Pinecone records never informed the new scores.

## Decision

Make the daily routine invoke the deterministic Workflow
(`scripts/portfolio-routine-workflow.js`) instead of the prose `/trade routine --cloud`
prompt. The routine prompt now only: runs setup (`./install.sh`, pip), generates the
run parameters, and calls the **Workflow** tool once with `args`.

This fixes the class of problem, not just the instances:

- **Deterministic control flow in code.** The 14-way parallel fan-out, the single
  shared payload builder (`build_sweep_payload.py`), signing, and delivery are encoded
  in a committed, code-reviewed, **testable** `.js`. The agent's judgment is confined to
  analysis *content*; the brittle plumbing is code.
- **One source of truth, version-controlled.** Changes ship via PRs + tests, not by
  editing prose in a routine config — eliminating the divergent-copies problem.
- **Memory-on-read.** Each ticker recalls its prior Pinecone record (STEP 0) before
  scoring, giving continuity the prose path lacked.
- **Correct, full-book outputs.** Full-book `portfolio_targets` + changed-only
  `signal_changes`, emitted deterministically.
- **Cleaner secrets & reproducibility.** Secrets are injected at runtime via
  `args.secrets` (held in the RemoteTrigger config, out of git); run params are
  deterministic; runs are journaled.

## Diligence before going live

- **Capability probe:** confirmed the CCR cloud sandbox exposes the Workflow tool and
  `agent()` fan-out (`workflow_tool=AVAILABLE | agent_fanout=OK`).
- **Two end-to-end validation runs** (validate-first, daily routine untouched until
  proven). The first surfaced an `args`-serialization bug — the Workflow runtime
  delivers `args` as a JSON **string**, so direct `args.run_id` / `args.secrets` access
  returned `undefined` and every field fell to its default (empty secrets → recall
  0/14, webhook `401`). Fixed by normalizing `args` (JSON.parse when string).
- **Re-validation green:** run `routine-20260627-1535-cec861` — real run id, recall
  working, webhook `202`, full-book `portfolio_targets`, Slack + Drive delivered.

## Consequences / follow-ups

- **Rollback:** the prior skill-based prompt is retained; restoring it and dropping
  `Workflow` from the routine's `allowed_tools` reverts instantly.
- **Token rotation (open):** the proxy token, Vercel bypass, and webhook HMAC secret
  were previously hardcoded in the `.js` and remain in git history — rotate them and
  update the routine prompt's `args.secrets`.
- **Gotcha to remember:** Workflow `.js` scripts receive `args` as a JSON string;
  always `JSON.parse` it before use.

## Appendix — old prompt excerpts: gaps & fixes

Trimmed excerpts from the previous RemoteTrigger prompt (**secrets redacted** — this is a
committed doc), each paired with the gap it created and how the Workflow removes it.

### 1. Whole-sweep orchestration delegated to the model

Old prompt:
```text
Invoke /trade routine --cloud --max-escalations 30 --no-options. The slice-8 cloud
branch handles everything:
  - Load holdings: invoke /trade holdings ...
  - For each ticker, asks `trade_memory.py recommend-tier <T>` and dispatches
    /trade analyze (5-agent fan-out) or /trade quick.
  - Escalates a quick to analyze when the signal changed ...
  - Posts the digest to Slack ...; uploads the digest to Drive ...
```
**Gap:** the loop, tiering, fan-out, and per-ticker dispatch are model-interpreted prose —
order, parallelism, and completeness vary run to run, and there is no schema on the
per-ticker result.

**Fix (workflow):** the fan-out is explicit, parallel, and schema-validated in code —
```js
const rawAnalyses = await parallel(HOLDINGS.map(h => () =>
  agent(buildAnalysisPrompt(h), { label: 'analyze:' + h.ticker, schema: ANALYSIS_SCHEMA })
))
```
Every result conforms to `ANALYSIS_SCHEMA` (signal enum, numeric scores), so downstream
steps consume structured data, not free text.

### 2. Step W inputs hand-assembled from a self-generated table

Old prompt:
```text
W1. Write the raw inputs, then build + validate via the installed script:

cat > /tmp/sweep_inputs.json <<'JSON'
{"rows": [], "holdings": [], "stops": [], "catalysts": []}
JSON

Fill from the delta table + the full Score Summary table (substitute real values ...):
- rows: one entry per ticker whose signal CHANGED this sweep ...
    {"ticker":"DIVO","prior_signal":"HOLD","new_signal":"BUY","new_score":71}
- holdings: one entry for EVERY holding ... Do NOT pre-filter ... ALWAYS populate it.
...
python3 .../build_sweep_payload.py sweep --run-id "PUT_RUN_ID_HERE" \
  --in /tmp/sweep_inputs.json --out /tmp/sweep_payload.json
```
**Gap:** the agent must transcribe its own prose tables into JSON by hand, remember to
populate `holdings` fully (or `portfolio_targets` silently degrades to changed-only), and
substitute the real run id for `PUT_RUN_ID_HERE`. This is exactly where partial-target and
`routine-unknown` failures originate.

**Fix (workflow):** the inputs derive from a structured summary the JS computes from the
schema-validated results, with priors from Pinecone recall and the run id passed in (no
placeholder) —
```js
const analysisSummary = analyses.map(a => ({
  ticker:          a.ticker,
  prior_signal:    a.prior_signal_recalled || priorByTicker[a.ticker] || 'NEUTRAL', // recall-derived
  new_signal:      a.signal,
  composite_score: a.composite_score,
  stop_loss:       a.stop_loss || null,
  // ...
}))
```
The delivery step maps this clean array to `rows` (changed-only) and `holdings` (full
book) — a mechanical transform, not free-hand transcription — then calls the same
`build_sweep_payload.py` with the real `RUN_ID`.

### 3. Webhook signing inlined in prose (hardcoded secret, drift-prone headers)

Old prompt (secret redacted):
```python
python3 - <<'PYH'
import hmac, hashlib, urllib.request, ...
url    = 'https://unthawed-keshia-...ngrok-free.dev'
secret = '<HMAC secret hardcoded in the prompt>'
...
sig = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
req = urllib.request.Request(url + '/webhook/sweep', data=body, method='POST',
    headers={'X-Webhook-Token': secret, 'X-Webhook-Signature': sig, ...})
PYH
```
**Gap:** the signing/header logic was duplicated as prose across routine copies; a
divergent copy used the wrong header (`X-Signature-SHA256`) and the webhook returned
`401`. The HMAC secret was hardcoded in the prompt.

**Fix (workflow):** signing lives in one code path with the correct headers fixed, and the
secret is injected at runtime via `args` (not committed) —
```js
const WEBHOOK_SECRET = SECRETS.webhookSecret || ''   // from args.secrets, not hardcoded
```
The header names and signing are constant in the script, so they cannot drift between runs
or copies.

| Issue (old prose) | Symptom seen | Workflow fix |
|---|---|---|
| Model-interpreted orchestration | run-to-run variance, no result schema | `parallel()` fan-out + `ANALYSIS_SCHEMA` |
| Hand-built Step W inputs | `routine-unknown`, partial `portfolio_targets` | inputs from computed `analysisSummary`; run id via `args` |
| Inlined signing, drifting copies | webhook `401` (`X-Signature-SHA256`) | one code path, fixed headers |
| Secrets in prompt/repo | exposure | injected via `args.secrets` |
