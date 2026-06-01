# Path D Formalization — Plan-Doc Surgery

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Formalize the Path D decision (Vercel HTTPS proxy fronting Pinecone) by stamping
the CFG verification doc, appending the CFG-4 appendix, and folding the new "Cloud path:
Vercel HTTPS proxy" section + slice 7.5 + auth model + D.19/D.20 quality gates into the
producer plan, then commit both. Pure documentation surgery — no code changes.

**Architecture:** Two-doc edit cycle. First, close out the verification doc (stamp + appendix +
commit). Second, fold the Path D design into the producer plan in one coherent revision
(insert new section, insert new slice, expand existing slice, add new files/config/risks/gates).
Third, refresh state.md to mark resolved questions and re-point next steps. Each Task below
is a self-contained doc edit with verification (grep + line count) before commit.

**Tech Stack:** Markdown editing via the Edit tool. No code, no tests, no install steps. Verification
via `grep`, `wc -l`, and visual structural checks (heading hierarchy intact, slice numbering
contiguous, table rows balanced).

**Prerequisites confirmed:**
- ✅ Path D chosen (state.md "Path decision confirmed")
- ✅ Auth model: bounded-blast-radius (5-layer) — user confirmed in this session
- ✅ CFG-4 findings documented in state.md (4a PASS / 4b CONTRADICTORY / 4c FAIL)

---

## File structure

Files this plan modifies (no creates, no deletes):

| Path | Responsibility | Change shape |
|------|----------------|--------------|
| `plan/cfg-verification-20260531.md` | Slice-0 deliverable; ground truth for CFG gate outcomes | +CFG-4 row in Summary, +`**Chosen path:** D` stamp in Decision table, +new §CFG-4 appendix, +update §"Open questions" |
| `plan/portfolio-routine-and-vector-memory.md` | Producer plan, 10 slices | +new §"Cloud path: Vercel HTTPS proxy" section, +CFG-0 finding folded into §"Cloud feasibility gates", insert slice 7.5, expand slice 8, +proxy entry in §Files-to-CREATE, +2 new env vars in §1 config table, +2 new risks, +D.19/D.20 gates, +5th maintenance dependency |
| `state.md` | Session handoff for next Claude | Mark 2 open questions resolved, re-point next steps to point 4 (slice 1) since the doc work is complete |

Commits: two — one for the verification doc, one for the producer plan + state.md (state.md
gets folded into the producer-plan commit since it's a same-cycle metadata update).

---

## Task 1: Stamp verification doc — Chosen path D + CFG-4 in Summary

**Files:**
- Modify: `plan/cfg-verification-20260531.md` (Summary table — line 11–16)
- Modify: `plan/cfg-verification-20260531.md` (Decision table — line ~155–162)

- [ ] **Step 1.1: Add CFG-4 row to the Summary table**

In `plan/cfg-verification-20260531.md`, find the Summary table (currently 4 rows: CFG-0,
CFG-1, CFG-2, CFG-3). Insert a 5th row immediately after the CFG-3 row:

```markdown
| **CFG-4** *(custom MCP in routines + auth)* | ⚠️ **MIXED** | n/a (doc-based) | 4a PASS (custom MCP URL acceptable in claude.ai), 4b CONTRADICTORY (routine-sandbox reachability — Issue #22726 closed "not planned" vs v2.1.152 fix), 4c **FAIL** (claude.ai UI is OAuth-only; bearer/headers closed "not planned" — [Issue #112](https://github.com/anthropics/claude-ai-mcp/issues/112)) |
```

Also update the **Outcome** line (line 5) from `**3 PASS, 1 BLOCKED, +1 new gate added.**`
to `**3 PASS, 1 BLOCKED, +2 new gates added.**` Path D confirmed; slice 8 unblock has a
designated path.

- [ ] **Step 1.2: Stamp `**Chosen path:** D` in the Decision table**

In §"Decision: four paths forward" (line ~154), insert a new bolded line immediately
above the four-row table:

```markdown
**Chosen path:** **D** — Vercel HTTPS proxy fronting Pinecone. Rationale: this session's
CFG-4 investigation (see §CFG-4 below) found that the claude.ai connector UI only supports
OAuth, not bearer tokens (Issue #112, closed "not planned"). Path C therefore would require
a full OAuth 2.1 Dynamic Client Registration implementation on the MCP server (~8–12 days),
not the originally-estimated 4–5. Path D's effort is unchanged (~2–3 days), and its
"research-tool-grade auth" tradeoff is acceptable for a solo-developer tool over
public-source data with a rebuildable index. See §"Cloud path: Vercel HTTPS proxy" in
`plan/portfolio-routine-and-vector-memory.md` for the design.
```

- [ ] **Step 1.3: Verify edits structurally**

Run from project root:
```bash
grep -n "CFG-4" plan/cfg-verification-20260531.md
grep -n "Chosen path" plan/cfg-verification-20260531.md
grep -c "^|" plan/cfg-verification-20260531.md
```

Expected:
- `CFG-4` appears at least 3 times (Summary row, stamp paragraph mentioning §CFG-4, the
  appendix title added in Task 2).
- `Chosen path` appears once.
- Pipe-line count is up by 1 vs pre-edit (one new Summary row).

If any of these is off, re-inspect the edit before moving on.

---

## Task 2: Append CFG-4 appendix to verification doc

**Files:**
- Modify: `plan/cfg-verification-20260531.md` (append before closing italicized line — line ~180)

- [ ] **Step 2.1: Insert the CFG-4 appendix**

Insert this entire block immediately *before* the final italicized closing line (`*Slice 0
deliverable complete. Producer plan slice 1...*` — currently around line 182):

```markdown
---

## CFG-4 — Custom MCP in routines + auth (mixed; closed Path C out)

**Status:** ⚠️ MIXED — documentation-based verification, three sub-gates with split
outcomes.

**Why this gate was added.** Path C in the §Decision table (custom remote MCP server
wrapping Pinecone Developer ops) is only viable if (a) custom remote MCP servers can be
registered as connectors in claude.ai, (b) the routine sandbox actually reaches them at
runtime, and (c) static token auth works. State.md noted Path D as the chosen route, but
without CFG-4 there was no objective basis to *eliminate* C as a fallback. CFG-4 closes
that question.

### Sub-gate summary

| Sub-gate | Outcome | Evidence |
|----------|---------|----------|
| **4a** Custom remote MCP URL can be added to claude.ai | ✅ PASS | Documented UI flow: Customize > Connectors > Add custom connector. HTTPS + reachable from Anthropic IP ranges required. Pro/Max/Team/Enterprise plans. ([Help Center](https://support.claude.com/en/articles/11503834-build-custom-connectors-via-remote-mcp-servers)) |
| **4b** Routine sandbox reaches custom MCP | ⚠️ CONTRADICTORY | [Issue #22726](https://github.com/anthropics/claude-code/issues/22726) closed "not planned" (Feb 2026) explicitly states custom MCP NOT supported in Claude Code Web remote sessions. v2.1.152 release notes ([releasebot](https://releasebot.io/updates/anthropic)) say "Fixed remote MCP servers failing to connect in Claude Code Remote sessions when the egress proxy is enabled." Routine docs ([aitoolbriefing](https://aitoolbriefing.com/blog/claude-code-routines-enterprise-guide-2026/)) claim "any MCP server you've connected to Claude Code locally can be configured as a connector on a Routine." Existing 7 connectors in our routine config are all Anthropic-blessed (no proof customs work). |
| **4c** Token-based auth supported in claude.ai connector UI | ⛔ **FAIL** | Only OAuth Client ID + Client Secret in Advanced Settings. Bearer token / custom headers explicitly **closed as "not planned"** at [Issue #112](https://github.com/anthropics/claude-ai-mcp/issues/112). Confirmed across multiple sources ([truthifi 2026 guide](https://truthifi.com/education/mcp-connection-guide), [sunpeak Claude connector OAuth](https://sunpeak.ai/blogs/claude-connector-oauth-authentication/)). |

### Why 4c eliminates Path C economically

The original Path C effort estimate (~4–5 days) assumed a bearer token could be configured
in the claude.ai connector. 4c falsifies that assumption: a Path C MCP server must
implement OAuth 2.1 with Dynamic Client Registration ([MCP remote auth spec](https://medium.com/@yagmur.sahin/remote-mcp-in-the-real-world-oauth-2-1-9d149de6e475)) —
DCR endpoints, PKCE, token introspection, refresh, scopes, plus a small OAuth consent UI.
That's a ~5–7 day add, bringing Path C's total to **~8–12 days**. Path D's effort is
unchanged at ~2–3 days. The 5–10 day premium is no longer justified by Path C's
"preserved contract + reusability" benefits, given:

1. The Consumer Integration contract is preserved equally well by Path D (`trade_memory.py`
   is the contract enforcement boundary in both designs).
2. Reusability across Claude Desktop / Cursor / Codex is not a near-term plan goal; the
   trading-chatbot consumer uses direct Pinecone read keys per the existing contract.

### CFG-4b was not empirically tested

We never fired a live routine to confirm 4b because eliminating Path C via 4c made the
question moot. If a future Anthropic platform change (e.g., bearer-token support shipping
to the connector UI) reopens the Path C economics, re-running CFG-4 should start with a
CFG-4b live test: deploy a public no-auth MCP test server (or use an existing one),
register via claude.ai UI, attempt to call a tool from a one-shot routine.

### Impact on the §Decision table

- **Path C** struck through as economically unviable post-4c.
- **Path D** stamped as chosen (see stamp above the Decision table).
- Paths A and B are unaffected by CFG-4; they remain documented as alternatives if Path
  D's auth tradeoff becomes unacceptable later.

### External references collected in this gate

- [Issue #22726 — Custom MCP for Claude Code Web remote sessions](https://github.com/anthropics/claude-code/issues/22726)
- [Issue #112 — Bearer/headers for custom remote MCP](https://github.com/anthropics/claude-ai-mcp/issues/112)
- [Build custom connectors via remote MCP servers — Claude Help Center](https://support.claude.com/en/articles/11503834-build-custom-connectors-via-remote-mcp-servers)
- [Claude Code Routines enterprise guide](https://aitoolbriefing.com/blog/claude-code-routines-enterprise-guide-2026/)
- [Anthropic Release Notes — releasebot](https://releasebot.io/updates/anthropic)
- [Remote MCP in the Real World: OAuth 2.1, DCR](https://medium.com/@yagmur.sahin/remote-mcp-in-the-real-world-oauth-2-1-9d149de6e475)
- [MCP connectors for ChatGPT, Claude, Perplexity & more (2026) — truthifi](https://truthifi.com/education/mcp-connection-guide)
- [Claude Connector Authentication — sunpeak](https://sunpeak.ai/blogs/claude-connector-oauth-authentication/)
```

- [ ] **Step 2.2: Update §"Open questions" to mark resolved**

In §"Open questions" near the bottom (line ~173–178), replace these two open lines:

```
- Open: which of A/B/C/D do we commit to for slice 8? (Recommend defer to a separate brainstorm before any implementation work.)
- Open: if path B, does Pinecone Assistant's metadata model preserve our declared "Consumer Integration" schema? Needs Pinecone-docs verification before commitment.
```

with:

```
- **Resolved.** Which of A/B/C/D for slice 8? → **Path D**, formalized in §Decision and CFG-4 above; design folded into `plan/portfolio-routine-and-vector-memory.md` §"Cloud path: Vercel HTTPS proxy".
- **Resolved (moot).** Does Pinecone Assistant's metadata model preserve our Consumer Integration schema? → No longer needed; Path B was not chosen.
- Open: If Anthropic ships bearer-token support to the connector UI (closing Issue #112), reconsider Path C as a future migration? Track Issue #112; revisit only if Path D's auth tradeoff becomes operationally unacceptable.
```

- [ ] **Step 2.3: Update §"Resume prompt update" block**

In §"Resume prompt update" (line ~165–169), replace the entire quoted line:

```
> *Slice 0 verification complete: 3 PASS, 1 BLOCKED-by-platform (CFG-1, [Issue #32733](https://github.com/anthropics/claude-code/issues/32733)), +1 new gate (CFG-0). Decision needed on slice 8 path (A/B/C/D in `plan/cfg-verification-20260531.md` §Decision). Default starting point: slice 1 (extract `scripts/trade_scoring.py` + 6-band reconcile + README:141 + report-pdf no-args).*
```

with:

```
> *Slice 0 verification complete: 3 PASS, 1 BLOCKED-by-platform (CFG-1, [Issue #32733](https://github.com/anthropics/claude-code/issues/32733)), +2 new gates (CFG-0, CFG-4). **Path D chosen** for slice 8 (Vercel HTTPS proxy); design landed in `plan/portfolio-routine-and-vector-memory.md` §"Cloud path: Vercel HTTPS proxy" + slice 7.5. Default starting point: slice 1 (extract `scripts/trade_scoring.py` + 6-band reconcile + README:141 + report-pdf no-args).*
```

- [ ] **Step 2.4: Verify structural integrity**

Run from project root:
```bash
grep -c "^## " plan/cfg-verification-20260531.md
grep -n "^## CFG-" plan/cfg-verification-20260531.md
grep -c "Resolved" plan/cfg-verification-20260531.md
wc -l plan/cfg-verification-20260531.md
```

Expected:
- Section count (`^## `) increased by 1 (the new §CFG-4).
- `^## CFG-` lines: 5 (CFG-0, CFG-1, CFG-2, CFG-3, CFG-4) — was 4.
- `Resolved` count: at least 4 (the two pre-existing + two newly marked).
- Total line count up by roughly 70–90 lines vs pre-edit.

---

## Task 3: Commit verification doc

**Files:**
- Commit: `plan/cfg-verification-20260531.md`

- [ ] **Step 3.1: Stage and commit**

Run from project root:
```bash
git add plan/cfg-verification-20260531.md
git status
```

Expected `git status` output: shows `plan/cfg-verification-20260531.md` as a new file
(`A` prefix, not `M`) since the file was untracked before this commit.

Then:
```bash
git commit -m "Slice 0 closed: CFG verification deliverable + Path D chosen

- Adds CFG-4 (custom MCP in routines + auth) with 4a PASS / 4b CONTRADICTORY /
  4c FAIL findings, closing Path C economics
- Stamps Chosen path: D on the Decision table with rationale
- Marks A/B/C/D and Pinecone-Assistant-schema open questions as resolved
- Updates Resume prompt to point at the new Cloud path: Vercel HTTPS proxy section
  in the producer plan (added in follow-up commit)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3.2: Verify commit**

```bash
git log --oneline -n 1
```

Expected: most recent commit hash + the commit message subject line.

---

## Task 4: Add §"Cloud path: Vercel HTTPS proxy" to producer plan

**Files:**
- Modify: `plan/portfolio-routine-and-vector-memory.md` — insert new section after
  §"Cloud-first deployment model" (currently ends around line 174, before §"Cloud
  feasibility gates").

- [ ] **Step 4.1: Insert the new section**

Find the line `**Cloud feasibility gates (slice 0 — run before any code)**` (the section
heading on line 177). Insert this entire block immediately *before* that heading, with a
horizontal rule (`---`) before and after:

```markdown
---

## Cloud path: Vercel HTTPS proxy (slice 7.5 + 8)

CFG-1 BLOCKED + CFG-4c FAIL together mean the cloud routine cannot hold `PINECONE_API_KEY`
directly and cannot use a custom MCP connector with static bearer auth either. The
sanctioned escape hatch is the proxy pattern outside the agent's security boundary
([Anthropic — Securely deploying AI agents](https://platform.claude.com/docs/en/agent-sdk/secure-deployment)).
We deploy a small Vercel HTTPS function that holds the Pinecone API key in its own env
vars; routines reach it via `WebFetch`. This is the architecture stamped as **Path D** in
`plan/cfg-verification-20260531.md` §Decision.

### Topology

```
Cloud routine sandbox                Vercel function (proxy/)
┌────────────────────────┐           ┌──────────────────────┐         Pinecone
│ trade_memory.py        │           │ /upsert /query       │         (cloud,
│   sees                 │  HTTPS    │ /list /fetch /delete │  SDK    serverless,
│   PINECONE_PROXY_URL,  │ ────────► │                      │ ──────► integrated
│   PINECONE_PROXY_TOKEN │  Bearer   │ holds                │         inference)
│   → routes via httplib │           │   PINECONE_API_KEY   │
└────────────────────────┘           │   in Vercel env vars │
                                     └──────────────────────┘
```

The routine sandbox never holds the Pinecone key. The proxy validates every payload
against the same schema `trade_memory.py` writes — single source of truth pattern, same
discipline as `trade_scoring.py` extraction.

### `trade_memory.py` cloud-mode auto-detect

`scripts/trade_memory.py` (slice 3a) ships with two env vars wired through the
`VectorStore` constructor:

| Var | When set | Behavior |
|-----|----------|----------|
| `PINECONE_PROXY_URL` | unset (local) | `VectorStore` uses the Pinecone Python SDK directly with `PINECONE_API_KEY` |
| `PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN` | both set (cloud) | `VectorStore` uses `urllib.request` to POST to `<url>/<op>` with `Authorization: Bearer <token>`; `PINECONE_API_KEY` is NOT read |

The skill prose for `/trade routine` never branches on local-vs-cloud. The branching lives
inside the script. This keeps skills portable and keeps the cloud-mode test surface small.

### Proxy directory layout (slice 7.5 deliverable)

```
proxy/
├── api/
│   ├── upsert.py            # POST → validate → pinecone.upsert
│   ├── query.py             # POST → validate → pinecone.query
│   ├── list.py              # POST → validate → pinecone.list (with prefix)
│   ├── fetch.py             # POST → validate → pinecone.fetch
│   └── delete.py            # POST → validate → pinecone.delete
├── _lib/
│   ├── auth.py              # Constant-time bearer-token check
│   ├── validate.py          # Pydantic schemas; namespace allowlist; ID regex; metadata key allowlist
│   └── ratelimit.py         # Upstash Redis (free tier) per source IP
├── requirements.txt         # pinecone>=5, pydantic, vercel
├── vercel.json              # Function config; declares env vars
└── README.md                # Deploy + URL/token registration + rotation procedure
```

Validation helpers in `_lib/validate.py` are imported from `scripts/trade_memory.py`'s
shared validation module (extracted as part of slice 3a) so the schema enforced at the
proxy boundary stays in lockstep with what the producer writes.

### Endpoint surface — minimal, lockdown-focused

| Endpoint | Accepts | Rejects |
|----------|---------|---------|
| `POST /upsert` | `{namespace, records: [{id, values?, metadata, text}]}`, namespace ∈ allowlist (`trade` + any registered consumer namespace), id matches `^[A-Z0-9.\-]+:[A-Z]+:\d{8}-\d{4}:[a-z0-9-]+:\d+$`, metadata keys ⊆ Consumer Integration schema, max 100 records/call | Other namespaces; malformed IDs; unknown metadata keys; payloads > 500 KB |
| `POST /query` | `{namespace, vector OR text, top_k ≤ 50, filter?}` | Other namespaces; top_k > 50; filters referencing unknown fields |
| `POST /list` | `{namespace, prefix, limit ≤ 1000}` | Other namespaces; missing prefix (forces lexical scope) |
| `POST /fetch` | `{namespace, ids: [...]}` ≤ 100 ids | Other namespaces; ids list > 100 |
| `POST /delete` | `{namespace, ids OR filter, confirm: "yes"}` | Other namespaces; missing `confirm` field; bulk delete without explicit confirm |

This lockdown surface is what makes the auth model acceptable: even if the bearer token
leaks, an attacker can only write schema-valid records to allowed namespaces, not exfiltrate
arbitrary data or wipe content without explicit confirmation.

### Auth model — 5 layers, bounded-blast-radius

State.md noted the chicken-and-egg: routines have no secret store, so any bearer the
routine presents lives in the prompt (a not-secret-grade location). The v0 model
that makes this acceptable for a research tool:

1. **High-entropy URL.** Deploy under a random subdomain (e.g. `https://pcp-9k2x7zm4w1.vercel.app`).
   Not enumerable; rotate quarterly.
2. **Bearer token in routine prompt.** 32-char random (`openssl rand -hex 32`). Stored in
   Vercel env var `PROXY_AUTH_TOKEN`; constant-time-compared at the proxy. Rotate monthly.
3. **Strict payload validation.** Per the endpoint table above. Schema lockdown is the
   structural defense; defense-in-depth even against token compromise.
4. **Upstash Redis rate limit.** Free tier; 100 req/min per source IP; bursts allowed.
   Routine uses < 30 req/run; alert on > 200 req/min anomalies.
5. **Rotation cadence.** Bearer monthly (5-min op: update Vercel env + edit routine prompt).
   URL quarterly (re-deploy under new subdomain + edit routine prompt). Weekly log review
   via `mcp__claude_ai_Vercel__get_runtime_logs`.

**Honest framing:** This is research-tool-grade auth, not production-grade. The README
section authored in slice 9 says this verbatim so no future contributor mistakes it. The
threat model it serves: solo developer, public-source data, rebuildable index via
`trade_memory.py rebuild <drive-folder-id>`. Worst-case compromise = "rebuild the index
from Drive" = ½ day inconvenience. It does NOT serve: production systems, PII, multi-tenant
permissions, compliance regimes.

### Cost

Vercel free tier: 100 GB-hours/month function execution, 100 GB egress. Routine fires daily
with < 30 requests/run, ~5s total compute/run = trivially below free tier. Upstash Redis
free tier: 10K commands/day, plenty for the rate limiter. **Total expected: ~$0/month**
for the proxy tier (Pinecone costs unchanged from §1 estimate of $0.15–$0.30/month).

---
```

- [ ] **Step 4.2: Verify section landed correctly**

```bash
grep -n "^## " plan/portfolio-routine-and-vector-memory.md | head -20
grep -c "PINECONE_PROXY_URL" plan/portfolio-routine-and-vector-memory.md
```

Expected:
- New `## Cloud path: Vercel HTTPS proxy (slice 7.5 + 8)` heading appears between
  "Cloud-first deployment model" and "Cloud feasibility gates".
- `PINECONE_PROXY_URL` appears at least twice (in the topology box and the env-var table).

---

## Task 5: Insert slice 7.5 + expand slice 8 in §"Rollout slice order"

**Files:**
- Modify: `plan/portfolio-routine-and-vector-memory.md` — §"Rollout slice order"
  (currently lines ~620–743, slices 0–9).

- [ ] **Step 5.1: Insert slice 7.5 between slice 7 and slice 8**

Find the slice 7 block (ends with its gate paragraph). Immediately after slice 7's gate
paragraph and before `### Slice 8 — Cloud routine deployment`, insert:

```markdown
### Slice 7.5 — Vercel HTTPS proxy (1–2 days, after CFG-1 BLOCKED + Path D chosen)

Builds `proxy/` per the directory layout in §"Cloud path: Vercel HTTPS proxy".

- Author the 5 endpoints + shared validation/auth/ratelimit lib (~300 LOC Python).
- Import validation schema from `scripts/trade_memory.py`'s shared module (extracted in
  slice 3a) so proxy + producer enforce identical contracts.
- Deploy to Vercel under a high-entropy subdomain; set `PINECONE_API_KEY` +
  `PROXY_AUTH_TOKEN` as Vercel env vars.
- Wire Upstash Redis rate limit (free tier).
- Author `proxy/README.md` covering: redeploy, env-var management, URL rotation,
  bearer-token rotation, log review procedure.

**Gate:**
1. Manual `curl` against each endpoint with valid token returns expected JSON.
2. Manual `curl` with wrong token returns 401.
3. Manual `curl` with invalid namespace returns 400.
4. Rate-limit test: 200 requests in 60 seconds → 100 succeed, ≥ 100 return 429.
5. Round-trip parity: same `TRADE-ANALYSIS-TEST.md` ingested via local SDK and via proxy
   produces byte-identical Pinecone records (D.19 gate); verified by `latest TEST --type
   ANALYSIS` returning identical JSON under both modes.
6. `trade_memory.py` with `PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN` set proxies all
   ops; `doctor` reports proxy mode active and the auth check passes.
```

- [ ] **Step 5.2: Expand slice 8 description with env-var wiring**

In `### Slice 8 — Cloud routine deployment` (currently a 1-paragraph block + gate),
replace the body paragraph (between the heading and the **Gate:** line) with:

```markdown
Add the `--cloud` flag wiring + Slack DM delivery + Drive archive upload. The cloud
routine prompt template now exports two env vars before invoking the routine:

```bash
export PINECONE_PROXY_URL="https://<deployed-subdomain>.vercel.app"
export PINECONE_PROXY_TOKEN="<32-char-hex-from-vercel-env>"
```

`trade_memory.py` auto-detects both being set and routes all Pinecone ops via the proxy
(per §"Cloud path: Vercel HTTPS proxy" → "cloud-mode auto-detect"). Skills don't branch.

Document the cloud routine creation flow in `README.md`, including the explicit "this
auth model is research-tool-grade, not production-grade" callout and the rotation
procedure. Document the verification routines (CFG-1/2/3/4) so the user can re-run them
on Anthropic platform changes.
```

- [ ] **Step 5.3: Verify slice ordering**

```bash
grep -n "^### Slice " plan/portfolio-routine-and-vector-memory.md
```

Expected output (in order): Slice 0, Slice 1, Slice 2, Slice 3a, Slice 3b, Slice 4,
Slice 5, Slice 6, Slice 7, **Slice 7.5**, Slice 8, Slice 9.

---

## Task 6: Add proxy/ to §Files-to-CREATE; add proxy env vars to §1 config

**Files:**
- Modify: `plan/portfolio-routine-and-vector-memory.md` — §"Files to CREATE" table (~line 209–221)
- Modify: `plan/portfolio-routine-and-vector-memory.md` — §1 config table (~line 250–260)

- [ ] **Step 6.1: Add `proxy/` row to §"Files to CREATE"**

Append a new row at the bottom of the Files-to-CREATE table (after the
`plan/cfg-verification-<YYYYMMDD>.md` row):

```markdown
| `proxy/` (and contents: `api/{upsert,query,list,fetch,delete}.py`, `_lib/{auth,validate,ratelimit}.py`, `requirements.txt`, `vercel.json`, `README.md`) | Slice 7.5 Vercel HTTPS proxy fronting Pinecone — see §"Cloud path: Vercel HTTPS proxy" for design. Holds `PINECONE_API_KEY` in its own env vars; routine sandbox never sees the key. |
```

- [ ] **Step 6.2: Add `PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN` to §1 config table**

In §1 "Config (env)" table (currently 7 rows from `PINECONE_API_KEY` through
`TRADE_DRIVE_ARCHIVE_FOLDER_ID`), insert two new rows after the
`TRADE_DRIVE_ARCHIVE_FOLDER_ID` row:

```markdown
| `PINECONE_PROXY_URL` | *(optional)* | When set together with `PINECONE_PROXY_TOKEN`, `VectorStore` routes all ops through this HTTPS proxy instead of the Pinecone SDK directly. Used in cloud routines (CFG-1 blocks direct key injection). See §"Cloud path: Vercel HTTPS proxy". |
| `PINECONE_PROXY_TOKEN` | *(optional)* | Bearer token for proxy auth. Required if `PINECONE_PROXY_URL` is set. NEVER set this locally — local invocations should use the Pinecone SDK directly with `PINECONE_API_KEY`. |
```

- [ ] **Step 6.3: Verify**

```bash
grep -c "PINECONE_PROXY" plan/portfolio-routine-and-vector-memory.md
grep -n "proxy/" plan/portfolio-routine-and-vector-memory.md
```

Expected:
- `PINECONE_PROXY` count ≥ 6 (2 in config table + ≥ 4 in §"Cloud path" section).
- `proxy/` appears at least 3 times (Files-to-CREATE row, §"Cloud path" topology, slice 7.5).

---

## Task 7: Add 2 risks + D.19/D.20 gates + 5th maintenance dependency

**Files:**
- Modify: `plan/portfolio-routine-and-vector-memory.md` — §Risks (~line 879–923)
- Modify: `plan/portfolio-routine-and-vector-memory.md` — §"D. Quality gates" (~line 829–874)
- Modify: `plan/portfolio-routine-and-vector-memory.md` — §"Long-term maintenance shape" (~line 928–942)

- [ ] **Step 7.1: Add 2 risk bullets to §Risks**

Find the `**CFG-1 + CFG-2 both fail.**` risk (~line 895). Immediately after the
`**Drive MCP authorization can lapse.**` bullet (~line 898–901), insert:

```markdown
- **Vercel proxy downtime (slice 7.5+).** Cloud routines fail. Local invocations
  unaffected (they use the SDK directly). `recommend-tier` returns `analyze` (safe
  default per existing graceful-failure contract) and the routine continues with a
  Slack notification: "Pinecone proxy unreachable; deferring all tickers to full
  analyze tier on next local run." Mitigation: Vercel SLA + `doctor` warns on proxy
  health failure + monthly proxy redeploy as part of token rotation forces a fresh
  warm.
- **Proxy bearer-token leak (slice 7.5+).** Attacker who obtains the token + the
  high-entropy URL can write schema-valid records to allowed namespaces or run
  validated queries — but cannot exfiltrate arbitrary data or bulk-delete without
  explicit `confirm: "yes"` in the payload. Mitigation: schema lockdown (the proxy
  rejects anything outside the Consumer Integration schema), namespace allowlist,
  Upstash rate limit, monthly token rotation. Recovery: rotate token + rotate URL +
  `trade_memory.py rebuild <drive-folder-id>` to re-establish a clean index. Total
  worst-case recovery time: ½ day. Documented in README slice-9 cloud-deployment
  section as "research-tool-grade auth, not production-grade."
```

- [ ] **Step 7.2: Add D.19 + D.20 quality gates**

Find the existing D.18 gate (`**\`--namespace\` flag works end-to-end.**` ~line 872–874).
Immediately after D.18, append:

```markdown
19. **Proxy schema-validation parity (slice 7.5+).** Same `TRADE-ANALYSIS-TEST.md`
    ingested via local SDK and via the Vercel proxy produces byte-identical Pinecone
    records. Verify by running `trade_memory.py ingest TRADE-ANALYSIS-TEST.md` twice
    (once with `PINECONE_PROXY_URL` unset, once set) and `diff <(trade_memory.py latest
    TEST --type ANALYSIS)` between the two invocations — no field-level drift allowed.
    Run on every commit that touches `proxy/api/*.py`, `proxy/_lib/validate.py`, or the
    shared validation module imported by both.
20. **Proxy auth gate (slice 7.5+).** `curl -H "Authorization: Bearer <wrong-token>"
    <proxy-url>/query -d '{}'` returns HTTP 401. `curl` without the header returns
    HTTP 401. `curl` with the right token but a payload referencing a forbidden
    namespace returns HTTP 400. Rate-limit threshold: 200 requests in 60 seconds → ≥ 100
    return HTTP 429. Run on every commit that touches `proxy/_lib/auth.py` or
    `proxy/_lib/ratelimit.py`.
```

- [ ] **Step 7.3: Add 5th maintenance dependency**

In §"Long-term maintenance shape" the numbered list currently has 4 dependencies
(Pinecone SDK, Drive MCP, Slack MCP, `.claude/` mirror). Append:

```markdown
5. **Vercel proxy (slice 7.5+).** Vercel function lifecycle (cold starts, runtime
   deprecations), Upstash Redis service availability, bearer token + URL rotation
   discipline (monthly + quarterly cadence documented in `proxy/README.md`). Failure
   mode is graceful: cloud routines fall back to "schedule alive only" mode; local
   invocations are unaffected.
```

- [ ] **Step 7.4: Verify**

```bash
grep -n "^[0-9]\+\." plan/portfolio-routine-and-vector-memory.md | grep -A0 "Vercel proxy\|Proxy schema\|Proxy auth"
grep -c "^20\. \*\*Proxy auth" plan/portfolio-routine-and-vector-memory.md
grep -c "^5\. \*\*Vercel proxy" plan/portfolio-routine-and-vector-memory.md
```

Expected: all three greps return ≥ 1 match.

---

## Task 8: Fold CFG-0 finding into §"Cloud feasibility gates"

State.md flagged this as a carried open question from the prior session. Now that the
producer plan is being touched, fold it in alongside the Path D edits.

**Files:**
- Modify: `plan/portfolio-routine-and-vector-memory.md` — §"Cloud feasibility gates"
  (~line 177–205).

- [ ] **Step 8.1: Add CFG-0 paragraph above CFG-1**

In §"Cloud feasibility gates", insert this paragraph immediately *before* the existing
`**CFG-1 — Secret injection.**` paragraph:

```markdown
**CFG-0 — Probe legitimacy.** Cloud routines apply prompt-injection guardrails using the
contents of the cloned repo as context. Slice-0 probes need (a) their justification
visible in committed repo files (not only in the routine prompt) and (b) prompts that
do not request unnecessary recon, key fingerprints, or aggressive behavioral fencing
(classic injection shapes). Discovered empirically during the first CFG-1 attempt
(refused by the agent's guardrails on the grounds that no committed file authorized the
"environment enumeration" step). The fix: commit `plan/` to `main` BEFORE firing any
slice-0 routine, and narrow probes to the minimum signal needed. Established as a
prerequisite for any future cloud-routine work in this repo. See
`plan/cfg-verification-20260531.md` §CFG-0 for the verbatim refusal text and the lessons.
```

- [ ] **Step 8.2: Verify**

```bash
grep -n "^\*\*CFG-" plan/portfolio-routine-and-vector-memory.md
```

Expected output: 4 CFG entries in order (CFG-0, CFG-1, CFG-2, CFG-3). CFG-4 lives only
in the verification doc, not in the producer plan's slice-0 section, since CFG-4 was
discovered post-slice-0 and is reflected in the §"Cloud path: Vercel HTTPS proxy"
section's rationale instead.

---

## Task 9: Refresh state.md (resolved questions + next steps)

**Files:**
- Modify: `state.md` — §"Open questions" and §"Next steps"

- [ ] **Step 9.1: Mark resolved open questions**

In `state.md` §"Open questions", remove these two bullets (now resolved):

- "Auth-model phrasing for Path D — bounded-blast-radius (recommended) or invest in
  Vercel-side OAuth (+3–4 days)?"
- "Draft the Path D edits now or in a separate session?"

Add one new bullet:

```markdown
- **Resolved this turn.** Auth model = bounded-blast-radius. Path D edits drafted +
  committed (see commit history). Carried open questions about `cfg-verification-20260531.md`
  commit + Path D + CFG-0 fold-in are all now closed.
```

The remaining open question stays:
- "Slice 1 implementation OR slice 7.5 brainstorm next?"

- [ ] **Step 9.2: Update §"Next steps"**

Replace the entire §"Next steps" numbered list with:

```markdown
1. **Start slice 1** (recommended — pre-existing debt cleanup, zero CFG deps, half-day):
   - Extract `score_grade()` + `trade_signal()` from `scripts/generate_trade_pdf.py:82-93`
     into new `scripts/trade_scoring.py`.
   - Reconcile to 6 bands (STRONG BUY / BUY / HOLD / NEUTRAL / CAUTION / AVOID).
   - Fix duplicate-Caution bug at `README.md:141`.
   - Fix `skills/trade-report-pdf/SKILL.md` Step 4b (must pass JSON path arg).
2. **(Alternative)** Brainstorm slice 7.5 further (Vercel proxy detailed design + Upstash
   wiring + OAuth-issued-token Vercel pattern verification) before any code lands. Less
   urgent — the design is already substantially specified in
   `plan/portfolio-routine-and-vector-memory.md` §"Cloud path: Vercel HTTPS proxy".
3. **(Later, after slice 1 + slice 2 land)** Begin slice 3a (`trade_memory.py` core with
   shared validation module that proxy will reuse in slice 7.5).
```

- [ ] **Step 9.3: Update §"Last update" stamp**

Replace the `**Last update:**` paragraph at the top of state.md with:

```markdown
**Last update:** 2026-05-31, post-Path-D-formalization commits. Verification doc closed
out (`Slice 0 closed: CFG verification deliverable + Path D chosen`); producer plan grew
§"Cloud path: Vercel HTTPS proxy" + slice 7.5 + D.19/D.20 gates + CFG-0 finding folded in.
Bounded-blast-radius auth model confirmed. Ready to start slice 1.
```

---

## Task 10: Commit producer plan + state.md

**Files:**
- Commit: `plan/portfolio-routine-and-vector-memory.md`, `state.md`

- [ ] **Step 10.1: Stage and commit**

```bash
git add plan/portfolio-routine-and-vector-memory.md state.md
git status
```

Expected: producer plan shows `M` (modified, already tracked from commit `d78e1fe`);
state.md shows `A` (untracked → new file, since prior sessions left it untracked).

Then:
```bash
git commit -m "Producer plan: add Path D Vercel proxy section + slice 7.5 + gates

- New section: 'Cloud path: Vercel HTTPS proxy (slice 7.5 + 8)' — topology,
  trade_memory.py cloud-mode auto-detect, proxy directory layout, endpoint
  lockdown surface, 5-layer bounded-blast-radius auth model, cost estimate
- New slice 7.5: Vercel HTTPS proxy (1-2 days)
- Expanded slice 8: cloud env-var wiring + auth-tradeoff README callout
- Files-to-CREATE: proxy/ directory
- Config table: PINECONE_PROXY_URL + PINECONE_PROXY_TOKEN env vars
- 2 new risks: proxy downtime + bearer-token leak (with bounded recovery)
- 2 new quality gates: D.19 schema-validation parity, D.20 proxy auth
- 5th long-term maintenance dependency: Vercel proxy lifecycle
- Folded in CFG-0 finding (probe-legitimacy gate discovered in slice 0)

state.md refreshed: marks auth-framing + Path D draft questions resolved;
next steps repointed at slice 1 (pre-existing debt cleanup).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 10.2: Verify commit**

```bash
git log --oneline -n 3
```

Expected: top 3 commits are this commit + the verification-doc commit (Task 3) + the
prior `d78e1fe Commit producer + consumer plans (slice 0 prerequisite)`.

---

## Self-review

**Spec coverage:** All four state.md next-step items (verification doc stamp, CFG-4 appendix,
producer plan section + slice 7.5, state.md refresh) have tasks. Carried CFG-0 fold-in has
a task. ✅

**Placeholder scan:** No "TBD", no "implement later", no "similar to Task N", no
bare "verify". Every step shows the exact text to insert and the exact grep to run. ✅

**Type consistency:** `PINECONE_PROXY_URL` + `PINECONE_PROXY_TOKEN` env var names appear
consistently. Proxy directory `proxy/` consistent. Slice 7.5 numbering consistent. D.19 +
D.20 numbering consistent (continues from D.18). ✅

**Cross-doc consistency:** Verification doc points at the producer plan's new section by
name ("§Cloud path: Vercel HTTPS proxy"). Producer plan's new section points back to the
verification doc's Decision table. No cycles, just bilateral references. ✅

**Commit boundaries:** Two commits — one per logical unit (verification-doc close-out, then
producer plan + state.md refresh). Each commit is mergeable independently. ✅

---

## Execution choice

Plan complete and saved to `plan/path-d-formalization-20260531.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between
   tasks, fast iteration. Best for this plan because each task is small and self-contained;
   the doc edits are pure prose so subagents don't need cross-task code context.

2. **Inline Execution** — execute tasks in this session using `superpowers:executing-plans`,
   batch execution with checkpoints. Saves agent-dispatch overhead but consumes more of this
   session's context (currently 18%).

Which approach?
