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
